from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from app.equipment_library import EquipmentLibrary, EquipmentLibraryError


def mesh_glb() -> bytes:
    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + indices
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}, {"buffer": 0, "byteOffset": len(positions), "byteLength": len(indices)}], "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}, {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}]}
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    return struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(encoded) + 8 + len(binary)) + struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(binary), b"BIN\x00") + binary


class EquipmentLibraryTests(unittest.TestCase):
    def test_registers_valid_rigid_weapon_and_persists_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sword.glb"
            source.write_bytes(mesh_glb())
            library = EquipmentLibrary(root / "equipment")
            record = library.register_local(source, "iron-sword", "Iron Sword", "WEAPON", "weapon_primary", primary_socket="hand_r")
            self.assertEqual(record["asset_type"], "WEAPON")
            self.assertTrue((root / "equipment" / "iron-sword" / "equipment.manifest.json").is_file())
            self.assertEqual(library.catalog()["assets"][0]["id"], "iron-sword")
            self.assertEqual(library.selected_assets(["iron-sword"])[0]["primary_socket"], "hand_r")

    def test_rejects_weapon_without_primary_socket(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sword.glb"
            source.write_bytes(mesh_glb())
            with self.assertRaises(EquipmentLibraryError):
                EquipmentLibrary(root / "equipment").register_local(source, "iron-sword", "Iron Sword", "WEAPON", "weapon_primary")
