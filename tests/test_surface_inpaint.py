"""Numerical invariants only; real character closeups remain the visual gate."""
import unittest
import numpy as np
from workers.hunyuan.surface_inpaint import fill_surface_pixels


class SurfaceInpaintTests(unittest.TestCase):
    def test_missing_texel_uses_surface_neighbor_not_adjacent_atlas_island(self):
        pixels = np.array([[[1., 0, 0], [0, 0, 0], [0, 0, 1.]]], dtype=np.float32)
        positions = np.array([[[0., 0, 0], [9.9, 0, 0], [10., 0, 0]]])
        surface = np.ones((1, 3), dtype=bool)
        observed = np.array([[True, False, True]])
        result = fill_surface_pixels(pixels, positions, surface, observed)
        np.testing.assert_array_equal(result[0, 1], [0, 0, 1])
        np.testing.assert_array_equal(result[observed], pixels[observed])
        np.testing.assert_array_equal(pixels[0, 1], [0, 0, 0])

    def test_padding_does_not_keep_unrelated_splat_colors_outside_surface(self):
        pixels = np.array([[[1., 0, 0], [0, 1., 0], [0, 0, 1.]]], dtype=np.float32)
        positions = np.zeros((1, 3, 3))
        surface = np.array([[False, True, False]])
        result = fill_surface_pixels(pixels, positions, surface, surface)
        np.testing.assert_array_equal(result, np.array([[[0, 1, 0]] * 3]))

    def test_no_observed_surface_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'No observed surface'):
            fill_surface_pixels(np.zeros((2, 2, 3)), np.zeros((2, 2, 3)),
                                np.ones((2, 2), dtype=bool), np.zeros((2, 2), dtype=bool))


if __name__ == '__main__':
    unittest.main()
