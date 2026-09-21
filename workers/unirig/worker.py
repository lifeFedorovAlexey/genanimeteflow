from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


def _wsl_path(path: Path) -> str:
    drive = path.drive.rstrip(":").lower()
    return f"/mnt/{drive}{path.as_posix()[2:]}"


def _run(command: list[str], cwd: Path, environment: dict[str, str] | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def _wsl_command(shell: str, distro: str, python_bin: str, unirig_root: Path, repo_root: Path, compat_root: Path, line: str) -> list[str]:
    setup = (
        f"export PYTHONPATH={shlex.quote(_wsl_path(repo_root))}:{shlex.quote(_wsl_path(compat_root))}:{shlex.quote(_wsl_path(unirig_root))}:$PYTHONPATH; "
        "export HF_HOME=/mnt/d/models/hf-cache; "
        f"cd {shlex.quote(_wsl_path(unirig_root))} && {line}"
    )
    return [shell, "-d", distro, "--", "bash", "-lc", setup]


def run(request: dict) -> dict:
    root_value = os.getenv("UNIRIG_ROOT")
    if not root_value:
        return {"ok": False, "category": "MODEL_MISSING", "error": "UNIRIG_ROOT is not configured"}
    root = Path(root_value).expanduser().resolve()
    if not (root / "run.py").is_file():
        return {"ok": False, "category": "MODEL_MISSING", "error": f"UniRig checkout is incomplete: {root}"}

    shell = os.getenv("UNIRIG_BASH") or shutil.which("bash")
    if not shell:
        return {"ok": False, "category": "WSL_OR_BASH_MISSING", "error": "Configure UNIRIG_BASH or install WSL for UniRig"}
    source = Path(str(request.get("source_mesh", ""))).expanduser().resolve()
    output_dir = Path(str(request.get("output_dir", ""))).expanduser().resolve()
    if not source.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Rig source mesh was not found: {source}"}
    output_dir.mkdir(parents=True, exist_ok=True)

    is_wsl = Path(shell).name.lower() in {"wsl", "wsl.exe"}
    if not is_wsl:
        return {"ok": False, "category": "WSL_OR_BASH_MISSING", "error": "UniRig currently requires the configured WSL CUDA runtime on Windows"}
    blender = os.getenv("BLENDER_PATH")
    if not blender or not Path(blender).is_file():
        return {"ok": False, "category": "BLENDER_MISSING", "error": "Blender is required to extract and merge the UniRig prediction"}

    distro = os.getenv("UNIRIG_DISTRO", "Ubuntu")
    python_bin = os.getenv("UNIRIG_WSL_PYTHON", "/opt/unirig-venv/bin/python")
    repo_root = Path(__file__).resolve().parents[2]
    compat_root = Path(__file__).resolve().parent / "compat"
    prediction_root = output_dir / "unirig" / source.stem
    prediction_root.mkdir(parents=True, exist_ok=True)
    raw_data = prediction_root / "raw_data.npz"
    skeleton_prediction = prediction_root / "predict_skeleton.npz"
    skin_prediction = prediction_root / "predict_skin.npz"
    rigged = output_dir / "rigged.glb"
    logs: list[dict] = []

    def execute(label: str, command: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
        return_code, stdout, stderr = _run(command, cwd, env)
        logs.append({"stage": label, "command": command, "return_code": return_code, "stdout": stdout[-12000:], "stderr": stderr[-12000:]})
        return return_code == 0

    extract_script = repo_root / "workers" / "unirig" / "blender_extract.py"
    extract_env = os.environ.copy()
    extract_env["UNIRIG_ROOT"] = str(root)
    if not execute(
        "extract",
        [blender, "-b", "--python", str(extract_script), "--", "--input", str(source), "--output", str(raw_data), "--target-faces", "50000"],
        repo_root,
        extract_env,
    ):
        return {"ok": False, "category": "UNIRIG_ERROR", "error": "UniRig Blender extraction failed", "logs": logs}

    skeleton_task = _wsl_path(root / "configs" / "task" / "quick_inference_skeleton_articulationxl_ar_256.yaml")
    skin_task = _wsl_path(root / "configs" / "task" / "quick_inference_unirig_skin.yaml")
    # UniRig's get_files joins the output root with the input stem.  Passing an
    # absolute input path would override that root on POSIX, so use the file
    # name while the extracted raw_data already lives under the expected stem.
    source_wsl = source.name
    prediction_parent_wsl = _wsl_path(prediction_root.parent)
    skeleton_command = _wsl_command(
        shell, distro, python_bin, root, repo_root, compat_root,
        " ".join([
            shlex.quote(python_bin), "-m", "workers.unirig.infer",
            f"--task={shlex.quote(skeleton_task)}", "--seed=42",
            f"--input={shlex.quote(source_wsl)}",
            f"--output={shlex.quote(_wsl_path(prediction_root / 'skeleton.fbx'))}",
            f"--npz-dir={shlex.quote(prediction_parent_wsl)}",
        ]),
    )
    if not execute("skeleton", skeleton_command, repo_root):
        return {"ok": False, "category": "UNIRIG_ERROR", "error": "UniRig skeleton inference failed", "logs": logs}
    generated_skeleton = prediction_root / "skeleton.npz"
    if generated_skeleton.is_file():
        shutil.copyfile(generated_skeleton, skeleton_prediction)
    if not skeleton_prediction.is_file():
        return {"ok": False, "category": "UNIRIG_OUTPUT_INVALID", "error": f"Skeleton prediction was not created: {skeleton_prediction}", "logs": logs}

    skin_command = _wsl_command(
        shell, distro, python_bin, root, repo_root, compat_root,
        " ".join([
            shlex.quote(python_bin), "-m", "workers.unirig.infer",
            f"--task={shlex.quote(skin_task)}", "--seed=42",
            f"--input={shlex.quote(source_wsl)}",
            f"--output={shlex.quote(_wsl_path(prediction_root / 'skin.fbx'))}",
            f"--npz-dir={shlex.quote(prediction_parent_wsl)}",
        ]),
    )
    if not execute("skin", skin_command, repo_root):
        return {"ok": False, "category": "UNIRIG_ERROR", "error": "UniRig skin inference failed", "logs": logs}
    generated_skin = prediction_root / "skin.npz"
    if generated_skin.is_file():
        shutil.copyfile(generated_skin, skin_prediction)
    if not skin_prediction.is_file():
        return {"ok": False, "category": "UNIRIG_OUTPUT_INVALID", "error": f"Skin prediction was not created: {skin_prediction}", "logs": logs}

    export_script = repo_root / "workers" / "unirig" / "blender_export.py"
    if not execute(
        "merge",
        [blender, "-b", "--python", str(export_script), "--", "--prediction", str(skeleton_prediction), "--source", str(source), "--output", str(rigged), "--mode", "rigged"],
        repo_root,
        extract_env,
    ):
        return {"ok": False, "category": "UNIRIG_ERROR", "error": "UniRig Blender merge failed", "logs": logs}
    if not rigged.is_file() or rigged.stat().st_size == 0:
        return {"ok": False, "category": "UNIRIG_OUTPUT_INVALID", "error": f"UniRig merge did not produce a non-empty GLB: {rigged}", "logs": logs}
    return {"ok": True, "provider": "UniRigProvider", "rigged_mesh": str(rigged), "skeleton": str(skeleton_prediction), "skin": str(skin_prediction), "logs": logs}


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
