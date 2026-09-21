from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from workers.common.worker_protocol import read_request, write_result


def run(request: dict) -> dict:
    blender = os.getenv("BLENDER_PATH") or shutil.which("blender")
    if not blender:
        return {"ok": False, "category": "BLENDER_MISSING", "error": "Blender executable was not found"}
    source = Path(str(request.get("source_mesh", ""))).expanduser().resolve()
    if not source.is_file():
        return {"ok": False, "category": "INPUT_MISSING", "error": f"Export source does not exist: {source}"}
    output = Path(str(request["glb_output"])).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="character-factory-export-", suffix=".json", dir=output.parent)
    os.close(descriptor)
    request_file = Path(name)
    try:
        request_file.write_text(json.dumps({**request, "source_mesh": str(source)}), encoding="utf-8")
        script = Path(__file__).resolve().parents[2] / "tools" / "blender" / "export.py"
        completed = subprocess.run([blender, "--background", "--factory-startup", "--python", str(script), "--", str(request_file)], capture_output=True, text=True, check=False)
    finally:
        request_file.unlink(missing_ok=True)
    marker = "CHARACTER_FACTORY_RESULT="
    result_line = next((line for line in reversed(completed.stdout.splitlines()) if line.startswith(marker)), None)
    if completed.returncode != 0:
        return {"ok": False, "category": "BLENDER_ERROR", "error": f"Blender exited with code {completed.returncode}", "stdout": completed.stdout, "stderr": completed.stderr}
    if result_line is None:
        return {"ok": False, "category": "EXPORT_PROTOCOL", "error": "Blender export script did not return a result marker", "stdout": completed.stdout, "stderr": completed.stderr}
    result = json.loads(result_line[len(marker):])
    return {**result, "stdout": completed.stdout, "stderr": completed.stderr}


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
