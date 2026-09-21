from __future__ import annotations

import json
import sys
from typing import Any


def read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("Worker request stdin is empty")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Worker request must be a JSON object")
    return value


def write_result(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
