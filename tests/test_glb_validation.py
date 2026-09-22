from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.validation.glb import validate_glb


def minimal_glb() -> bytes:
    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + indices
    document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}, {"buffer": 0, "byteOffset": len(positions), "byteLength": len(indices)}], "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}, {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}]}
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    total_length = 12 + 8 + len(encoded) + 8 + len(binary)
    return struct.pack("<4sII", b"glTF", 2, total_length) + struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(binary), b"BIN\x00") + binary


def textured_glb(include_uv: bool) -> bytes:
    positions = struct.pack("<9f", 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    uv = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    indices = struct.pack("<3H", 0, 1, 2)
    chunks = [positions]
    attributes = {"POSITION": 0}
    if include_uv:
        attributes["TEXCOORD_0"] = 1
        chunks.append(uv)
    index_view = len(chunks)
    chunks.append(indices)
    binary = b"".join(chunks)
    views = []
    offset = 0
    for chunk in chunks:
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(chunk)})
        offset += len(chunk)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            *([{"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"}] if include_uv else []),
            {"bufferView": index_view, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": index_view, "mimeType": "image/png"}],
        "meshes": [{"primitives": [{"attributes": attributes, "indices": 2 if include_uv else 1, "material": 0}]}],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    total_length = 12 + 8 + len(encoded) + 8 + len(binary)
    return struct.pack("<4sII", b"glTF", 2, total_length) + struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(binary), b"BIN\x00") + binary


class GlbValidationTests(unittest.TestCase):
    def test_validates_embedded_mesh_and_indices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unit.glb"
            path.write_bytes(minimal_glb())
            report = validate_glb(path)
            self.assertTrue(report.valid)
            self.assertEqual(report.vertex_count, 3)
            self.assertEqual(report.face_count, 1)

    def test_rejects_invalid_magic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.glb"
            path.write_bytes(b"not a glb")
            report = validate_glb(path)
            self.assertFalse(report.valid)
            self.assertTrue(report.errors)

    def test_requires_uvs_for_textured_primitives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with_uv = root / "with_uv.glb"
            with_uv.write_bytes(textured_glb(include_uv=True))
            report = validate_glb(with_uv)
            self.assertTrue(report.valid)
            self.assertEqual(report.uv_primitive_count, 1)

            without_uv = root / "without_uv.glb"
            without_uv.write_bytes(textured_glb(include_uv=False))
            report = validate_glb(without_uv)
            self.assertFalse(report.valid)
            self.assertEqual(report.missing_uv_primitive_count, 1)
            self.assertTrue(any("TEXCOORD_0" in error for error in report.errors))
