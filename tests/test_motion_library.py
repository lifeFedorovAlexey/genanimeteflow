from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from app.motion_library import MotionLibrary


def animated_glb() -> bytes:
    key_times = struct.pack("<2f", 0.0, 1.0)
    values = struct.pack("<6f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    binary = key_times + values
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(key_times)}, {"buffer": 0, "byteOffset": len(key_times), "byteLength": len(values)}], "accessors": [{"bufferView": 0, "componentType": 5126, "count": 2, "type": "SCALAR"}, {"bufferView": 1, "componentType": 5126, "count": 2, "type": "VEC3"}], "animations": [{"name": "Idle", "samplers": [{"input": 0, "output": 1}], "channels": []}]}
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    return struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(encoded) + 8 + len(binary)) + struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(binary), b"BIN\x00") + binary


class MotionLibraryTests(unittest.TestCase):
    def test_recommended_clips_choose_real_canonical_roles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = {
                "schema_version": 1,
                "libraries": [{
                    "id": "fixture",
                    "license": "CC0",
                    "allowed_for_commercial_use": True,
                    "clips": [
                        {"id": "idle", "name": "Idle_Loop"},
                        {"id": "walk", "name": "Walk_Loop"},
                        {"id": "sprint", "name": "Sprint_Loop"},
                        {"id": "jump-start", "name": "Jump_Start"},
                        {"id": "jump-air", "name": "Jump_Loop"},
                        {"id": "jump-land", "name": "Jump_Land"},
                        {"id": "attack", "name": "Melee_Hook"},
                        {"id": "hit", "name": "Hit_Knockback"},
                        {"id": "death", "name": "Death01"},
                    ],
                }],
                "sources": [],
            }
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            library = MotionLibrary(catalog_path, root / "installed")
            self.assertEqual(library.recommended_clips(), ["idle", "walk", "sprint", "jump-start", "jump-air", "jump-land", "attack", "hit", "death"])

    def test_registers_local_glb_with_checksum_and_clip_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "motions.glb"
            source.write_bytes(animated_glb())
            library = MotionLibrary(root / "catalog.json", root / "installed")
            (root / "catalog.json").write_text(json.dumps({"schema_version": 1, "libraries": [], "sources": []}), encoding="utf-8")
            record = library.register_local(source, "test-library", "cmu-mocap", "test license", True)
            self.assertEqual(record["validation"]["clip_count"], 1)
            self.assertEqual(record["clips"][0]["name"], "Idle")
            self.assertEqual(record["clips"][0]["duration"], 1.0)
            self.assertEqual(len(record["source_sha256"]), 64)
            self.assertEqual(library.clips()["test-library:motions:0"]["library_id"], "test-library")
            self.assertEqual(library.clips()["test-library:motions:0"]["category"], "idle")
            self.assertEqual(library.selected_clips(["test-library:motions:0"])[0]["name"], "Idle")
