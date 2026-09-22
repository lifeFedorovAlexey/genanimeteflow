from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app import main
from app.job_store import JobStore
from app.schemas import JobCreateRequest


class SecurityTests(unittest.TestCase):
    def test_job_store_rejects_traversal_and_absolute_job_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary))
            candidates = ["../outside", "..\\outside", str(Path(temporary).parent / "outside")]
            for candidate in candidates:
                with self.assertRaises(ValueError):
                    store.job_dir(candidate)

    def test_job_file_rejects_paths_outside_job_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            previous_store = main.store
            try:
                main.store = JobStore(Path(temporary))
                manifest = main.store.create(JobCreateRequest())
                with self.assertRaises(HTTPException) as context:
                    main.job_file(manifest.job_id, "../outside.txt")
                self.assertEqual(context.exception.status_code, 400)
            finally:
                main.store = previous_store


if __name__ == "__main__":
    unittest.main()
