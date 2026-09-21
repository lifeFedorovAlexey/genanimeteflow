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


def _run(command: list[str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def run(request: dict) -> dict:
    root_value = os.getenv("UNIRIG_ROOT")
    if not root_value:
        return {"ok": False, "category": "MODEL_MISSING", "error": "UNIRIG_ROOT is not configured"}
    root = Path(root_value).expanduser().resolve()
    skeleton_script = root / "launch" / "inference" / "generate_skeleton.sh"
    skin_script = root / "launch" / "inference" / "generate_skin.sh"
    merge_script = root / "launch" / "inference" / "merge.sh"
    missing = [str(path) for path in (skeleton_script, skin_script, merge_script) if not path.is_file()]
    if missing:
        return {"ok": False, "category": "MODEL_MISSING", "error": "UniRig official inference scripts are missing: " + ", ".join(missing)}
    shell = os.getenv("UNIRIG_BASH") or shutil.which("bash")
    if not shell:
        return {"ok": False, "category": "WSL_OR_BASH_MISSING", "error": "Configure UNIRIG_BASH or install a bash/WSL runtime for UniRig"}
    source = Path(str(request.get("source_mesh", ""))).expanduser().resolve()
    output_dir = Path(str(request.get("output_dir", ""))).expanduser().resolve()
    if not source.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Rig source mesh was not found: {source}"}
    output_dir.mkdir(parents=True, exist_ok=True)
    skeleton = output_dir / "skeleton.fbx"
    skin = output_dir / "skin.fbx"
    rigged = output_dir / "rigged.glb"
    is_wsl = Path(shell).name.lower() in {"wsl", "wsl.exe"}
    if is_wsl:
        distro = os.getenv("UNIRIG_DISTRO", "Ubuntu")
        python_bin = os.getenv("UNIRIG_WSL_PYTHON", "/opt/unirig-venv/bin/python")
        compat_root = _wsl_path(Path(__file__).resolve().parent / "compat")

        def command(script: Path, args: list[tuple[str, Path]]) -> list[str]:
            script_text = shlex.quote(_wsl_path(script))
            arguments = " ".join(f"{shlex.quote(flag)} {shlex.quote(_wsl_path(value))}" for flag, value in args)
            shell_line = f"export PATH={shlex.quote(str(Path(python_bin).parent))}:$PATH; export PYTHONPATH={shlex.quote(compat_root)}:$PYTHONPATH; cd {shlex.quote(_wsl_path(root))} && bash {script_text} {arguments}"
            return [shell, "-d", distro, "--", "bash", "-lc", shell_line]

        commands = [
            command(skeleton_script, [("--input", source), ("--output", skeleton)]),
            command(skin_script, [("--input", skeleton), ("--output", skin)]),
            command(merge_script, [("--source", skin), ("--target", source), ("--output", rigged)]),
        ]
    else:
        commands = [
            [shell, str(skeleton_script), "--input", str(source), "--output", str(skeleton)],
            [shell, str(skin_script), "--input", str(skeleton), "--output", str(skin)],
            [shell, str(merge_script), "--source", str(skin), "--target", str(source), "--output", str(rigged)],
        ]
    logs: list[dict] = []
    for command in commands:
        return_code, stdout, stderr = _run(command, root)
        logs.append({"command": command, "return_code": return_code, "stdout": stdout, "stderr": stderr})
        if return_code != 0:
            combined = stdout + "\n" + stderr
            category = "FAILED_OOM" if "out of memory" in combined.lower() else "UNIRIG_ERROR"
            return {"ok": False, "category": category, "error": f"UniRig command failed with code {return_code}", "logs": logs}
    if not rigged.is_file() or rigged.stat().st_size == 0:
        return {"ok": False, "category": "UNIRIG_OUTPUT_INVALID", "error": f"UniRig merge did not produce a non-empty GLB: {rigged}", "logs": logs}
    return {"ok": True, "provider": "UniRigProvider", "rigged_mesh": str(rigged), "skeleton": str(skeleton), "skin": str(skin), "logs": logs}


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
