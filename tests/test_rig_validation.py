from __future__ import annotations

import unittest

from tools.validation.rig import canonical_mapping


class RigValidationTests(unittest.TestCase):
    def test_maps_canonical_bones_and_preserves_secondary_bones(self) -> None:
        mapping, extras = canonical_mapping(["root", "mixamorig:Hips", "mixamorig:Spine", "hair_01", "tail_01"])
        self.assertEqual(mapping["root"], "root")
        self.assertEqual(mapping["hips"], "mixamorig:Hips")
        self.assertIn("hair_01", extras)
        self.assertIn("tail_01", extras)
