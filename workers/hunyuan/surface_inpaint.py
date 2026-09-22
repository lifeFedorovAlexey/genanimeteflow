"""Fill unobserved texels on the mesh surface, then extend UV island borders.

Unlike image inpainting, proximity in the atlas is not used to infer the
color of an unobserved surface: adjacent islands can be unrelated body parts.
"""
import numpy as np


def surface_inpaint(renderer, texture, mask):
    import torch

    features = torch.cat([renderer.vtx_pos, torch.ones_like(renderer.vtx_pos[:, :1])], dim=1)
    mapped = renderer.uv_feature_map(features).detach().cpu().numpy()
    positions = mapped[..., :3]
    surface = mapped[..., 3] > .5
    pixels = fill_surface_pixels(texture.detach().cpu().numpy(), positions, surface, mask > 0)
    return torch.from_numpy(pixels).to(device=texture.device, dtype=texture.dtype)


def fill_surface_pixels(pixels, positions, surface, observed):
    from scipy.ndimage import distance_transform_edt
    from scipy.spatial import cKDTree

    pixels = np.asarray(pixels).copy()
    known = surface & observed
    missing = surface & ~known
    if not known.any():
        raise ValueError('No observed surface texels; refusing to invent a texture')
    if missing.any():
        tree = cKDTree(positions[known])
        _, nearest = tree.query(positions[missing], k=1, workers=4)
        pixels[missing] = pixels[known][nearest]
    # Guard bands are derived only from surface texels, never from the original
    # splat outside islands. This prevents colors from bleeding across seams.
    nearest = distance_transform_edt(~surface, return_distances=False, return_indices=True)
    pixels[~surface] = pixels[nearest[0][~surface], nearest[1][~surface]]
    return pixels
