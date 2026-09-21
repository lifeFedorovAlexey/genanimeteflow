from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerResult:
    payload: dict
    stdout: str
    stderr: str
    return_code: int


class WorkerFailure(RuntimeError):
    def __init__(self, category: str, message: str, result: WorkerResult | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.result = result


class ProcessManager:
    def run_json_worker(self, command: list[str], request: dict, cwd: Path, env: dict[str, str], log_path: Path, timeout_seconds: int = 3600) -> WorkerResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        process_env = os.environ.copy()
        process_env.update(env)
        try:
            completed = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True, cwd=cwd, env=process_env, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise WorkerFailure("WORKER_TIMEOUT", f"Worker exceeded timeout of {timeout_seconds} seconds") from exc
        log_path.write_text(f"COMMAND: {command}\n\nSTDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}\n", encoding="utf-8")
        result = WorkerResult(payload={}, stdout=completed.stdout, stderr=completed.stderr, return_code=completed.returncode)
        if completed.returncode != 0:
            category = "FAILED_OOM" if self._is_oom(completed.stdout + completed.stderr) else "WORKER_EXIT"
            raise WorkerFailure(category, f"Worker exited with code {completed.returncode}", result)
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise WorkerFailure("WORKER_PROTOCOL", "Worker did not return a JSON protocol response", result) from exc
        result = WorkerResult(payload=payload, stdout=completed.stdout, stderr=completed.stderr, return_code=completed.returncode)
        if not payload.get("ok", False):
            raise WorkerFailure(str(payload.get("category", "WORKER_ERROR")), str(payload.get("error", "Worker reported an error")), result)
        return result

    @staticmethod
    def _is_oom(output: str) -> bool:
        lowered = output.lower()
        return "out of memory" in lowered or "cuda error: out of memory" in lowered or "cuda_out_of_memory" in lowered
