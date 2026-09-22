from __future__ import annotations

import json
import sys

from app.acceptance import validate_job
from app.job_store import JobStore


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_acceptance.py JOB_ID", file=sys.stderr)
        return 2
    store = JobStore()
    try:
        manifest = store.get(sys.argv[1])
    except (FileNotFoundError, ValueError):
        print(json.dumps({"valid": False, "error": "Job not found"}, ensure_ascii=False))
        return 1
    result = validate_job(manifest, store.job_dir(manifest.job_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
