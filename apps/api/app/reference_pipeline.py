from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


SUPPORTED_VIEWS = ("front", "left", "back", "right")


def _foreground_mask(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    existing_alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    corners = [rgb.getpixel((x, y)) for x, y in ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1))]
    bg = tuple(sum(pixel[index] for pixel in corners) // len(corners) for index in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    color_mask = diff.point(lambda value: 255 if value > 18 else 0)
    if existing_alpha.getbbox() and any(value < 255 for value in existing_alpha.getdata()):
        return ImageChops.multiply(existing_alpha, color_mask)
    return color_mask


def _row_span(alpha: Image.Image, y: int) -> int:
    """Return the occupied width of one alpha row, ignoring transparent pixels."""
    row = alpha.crop((0, y, alpha.width, y + 1))
    bbox = row.getbbox()
    return (bbox[2] - bbox[0]) if bbox else 0


def _half_has_foreground(alpha: Image.Image, left: int, right: int, top: int, bottom: int) -> bool:
    return alpha.crop((left, top, right, bottom)).getbbox() is not None


def preprocess_reference(source: Path, destination: Path, resolution: int) -> dict[str, Any]:
    if resolution not in {384, 512, 640, 768}:
        raise ValueError("resolution must be one of 384, 512, 640, 768")
    with Image.open(source) as loaded:
        image = loaded.convert("RGBA")
        mask = _foreground_mask(image)
        bbox = mask.getbbox()
        if bbox is None:
            raise ValueError("reference has no detectable foreground")
        cropped = image.crop(bbox)
        cropped.putalpha(mask.crop(bbox))
        canvas_size = max(cropped.width, cropped.height)
        canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        canvas.alpha_composite(cropped, ((canvas_size - cropped.width) // 2, (canvas_size - cropped.height) // 2))
        output = canvas.resize((resolution, resolution), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        output.save(destination, "PNG", optimize=True)
        alpha = output.getchannel("A")
        alpha_bbox = alpha.getbbox()
        foreground_ratio = (alpha.getbbox() and sum(1 for value in alpha.getdata() if value > 10) / (resolution * resolution)) or 0.0
        return {
            "source_size": [image.width, image.height],
            "processed_size": [resolution, resolution],
            "foreground_bbox": list(alpha_bbox) if alpha_bbox else None,
            "foreground_ratio": round(foreground_ratio, 4),
            "alpha_pixels": int(sum(1 for value in alpha.getdata() if value > 10)),
        }


def assess_reference(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        ratio = (sum(1 for value in alpha.getdata() if value > 10) / (image.width * image.height)) if image.width and image.height else 0
        warnings: list[str] = []
        errors: list[str] = []
        if bbox is None or ratio == 0:
            errors.append("No foreground pixels detected")
            metrics = {
                "bbox_width_ratio": 0.0,
                "bbox_height_ratio": 0.0,
                "upper_body_span_ratio": 0.0,
                "left_side_foreground": False,
                "right_side_foreground": False,
            }
        else:
            left, top, right, bottom = bbox
            bbox_width = right - left
            bbox_height = bottom - top
            upper_rows = range(
                max(0, top + int(bbox_height * 0.20)),
                min(image.height, top + int(bbox_height * 0.62)),
            )
            widest_upper_row = max((_row_span(alpha, y) for y in upper_rows), default=0)
            upper_span_ratio = widest_upper_row / max(1, bbox_width)
            body_midpoint = left + bbox_width // 2
            metrics = {
                "bbox_width_ratio": round(bbox_width / max(1, image.width), 4),
                "bbox_height_ratio": round(bbox_height / max(1, image.height), 4),
                "upper_body_span_ratio": round(upper_span_ratio, 4),
                "left_side_foreground": _half_has_foreground(alpha, 0, max(1, body_midpoint), top, bottom),
                "right_side_foreground": _half_has_foreground(alpha, min(image.width - 1, body_midpoint), image.width, top, bottom),
            }
            if top <= 1:
                warnings.append("Head may touch the top edge")
            if bottom >= image.height - 1:
                warnings.append("Feet may touch the bottom edge")
            if bbox_height / max(1, image.height) < 0.72:
                warnings.append("The full character does not occupy enough vertical space")
            if not metrics["left_side_foreground"] or not metrics["right_side_foreground"]:
                warnings.append("Both sides of the character are not clearly visible")
            if upper_span_ratio < 0.30 or bbox_width / max(1, image.width) < 0.30:
                warnings.append("Arms may not be visible in an approximate T-pose")
            if ratio < 0.03:
                warnings.append("Foreground occupies very little of the image")
            if ratio > 0.95:
                warnings.append("Background removal did not isolate a foreground")
        level = "ERROR" if errors else ("WARNING" if warnings else "GOOD")
        return {"level": level, "warnings": warnings, "errors": errors, "foreground_ratio": round(ratio, 4), "size": [image.width, image.height], "bbox": list(bbox) if bbox else None, "silhouette": metrics}
