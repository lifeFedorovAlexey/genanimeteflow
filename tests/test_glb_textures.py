from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools.validation.glb import extract_glb_images


class GlbTextureTests(unittest.TestCase):
    def test_extracts_embedded_image_bytes_without_creating_maps(self) -> None:
        image_bytes = b"PNG_BYTES_FROM_PROVIDER"
        document = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(image_bytes)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(image_bytes)}], "images": [{"bufferView": 0, "mimeType": "image/png", "name": "baseColor"}]}
        encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
        encoded += b" " * ((4 - len(encoded) % 4) % 4)
        binary = image_bytes + b"\x00" * ((4 - len(image_bytes) % 4) % 4)
        glb = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(encoded) + 8 + len(binary)) + struct.pack("<I4s", len(encoded), b"JSON") + encoded + struct.pack("<I4s", len(binary), b"BIN\x00") + binary
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "unit.glb"
            source.write_bytes(glb)
            extracted = extract_glb_images(source, root / "textures")
            self.assertEqual(len(extracted), 1)
            self.assertEqual((root / "textures" / "image_000.png").read_bytes(), image_bytes)
