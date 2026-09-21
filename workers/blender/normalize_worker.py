from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


def run(request: dict) -> dict:
    blender = os.getenv("BLENDER_PATH") or shutil.which("blender")
    if not blender:
        return {"ok": False, "category": "BLENDER_MISSING", "error": "Blender executable was not found"}
    source = Path(str(request.get("source_motion", ""))).expanduser().resolve()
    target = Path(str(request.get("target_rig", ""))).expanduser().resolve()
    if not source.is_file() or not target.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": "Source motion and target rig files must exist"}
    output = Path(str(request["output_mesh"])).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="character-factory-normalize-", suffix=".json", dir=output.parent)
    os.close(descriptor)
    request_file = Path(name)
    try:
        request_file.write_text(json.dumps({**request, "source_motion": str(source), "target_rig": str(target), "output_mesh": str(output)}), encoding="utf-8")
        script = Path(__file__).resolve().parents[2] / "tools" / "blender" / "normalize_motion.py"
        completed = subprocess.run([blender, "--background", "--factory-startup", "--python", str(script), "--", str(request_file)], capture_output=True, text=True, check=False)
    finally:
        request_file.unlink(missing_ok=True)
    marker = "CHARACTER_FACTORY_RESULT="
    result_line = next((line for line in reversed(completed.stdout.splitlines()) if line.startswith(marker)), None)
    if completed.returncode != 0:
        return {"ok": False, "category": "BLENDER_ERROR", "error": f"Blender exited with code {completed.returncode}", "stdout": completed.stdout, "stderr": completed.stderr}
    if result_line is None:
        return {"ok": False, "category": "NORMALIZATION_PROTOCOL", "error": "Blender normalization script did not return a result marker", "stdout": completed.stdout, "stderr": completed.stderr}
    return {**json.loads(result_line[len(marker):]), "stdout": completed.stdout, "stderr": completed.stderr}


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
