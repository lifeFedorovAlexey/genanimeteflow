from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from workers.common.worker_protocol import read_request, write_result


def _cosine(left: list[float], right: list[float]) -> float:
    import math

    if not all(math.isfinite(value) for value in left + right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def run(request: dict[str, Any]) -> dict[str, Any]:
    images = request.get("images")
    model_path = Path(str(request.get("model_path", ""))).expanduser().resolve()
    if not isinstance(images, dict) or len(images) < 2:
        return {"ok": True, "available": False, "reason": "At least two processed views are required"}
    if not model_path.is_dir():
        return {"ok": False, "category": "MODEL_MISSING", "error": f"DINOv3 model path was not found: {model_path}"}
    selected: dict[str, Path] = {}
    for view, value in images.items():
        path = Path(str(value)).expanduser().resolve()
        if not path.is_file():
            return {"ok": False, "category": "INPUT_MISSING", "error": f"Processed {view} reference was not found: {path}"}
        selected[str(view)] = path
    try:
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModel

        device = "cuda" if torch.cuda.is_available() else "cpu"
        processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True)
        # DINOv3 ViT-L produces NaNs on this RTX 4070 when the frozen encoder is
        # converted wholesale to fp16. Keep its weights in fp32; the model is
        # still small enough for the dedicated reference-quality worker.
        model = AutoModel.from_pretrained(model_path, local_files_only=True)
        model.eval().to(device)
        with torch.inference_mode():
            embeddings: dict[str, list[float]] = {}
            for view, path in selected.items():
                with Image.open(path) as image:
                    batch = processor(images=image.convert("RGB"), return_tensors="pt")
                batch = {key: value.to(device) for key, value in batch.items()}
                output = model(**batch)
                vector = output.last_hidden_state[:, 0, :].float()
                vector = torch.nan_to_num(torch.nn.functional.normalize(vector, dim=-1), nan=0.0, posinf=0.0, neginf=0.0)[0].cpu().tolist()
                embeddings[view] = vector
        pairs: list[dict[str, Any]] = []
        views = list(embeddings)
        for index, left in enumerate(views):
            for right in views[index + 1 :]:
                pairs.append({"views": [left, right], "cosine": round(_cosine(embeddings[left], embeddings[right]), 5)})
        import math

        scores = [float(pair["cosine"]) for pair in pairs if math.isfinite(float(pair["cosine"]))]
        mean_score = sum(scores) / len(scores) if scores else 1.0
        min_score = min(scores) if scores else 1.0
        # This is an input-consistency warning, not a geometry-quality verdict.
        level = "WARNING" if not scores or min_score < 0.45 or mean_score < 0.58 else "GOOD"
        return {
            "ok": True,
            "available": True,
            "model_id": "facebook/dinov3-vitl16-pretrain-lvd1689m",
            "views": views,
            "pairwise": pairs,
            "mean_cosine": round(mean_score, 5),
            "min_cosine": round(min_score, 5),
            "level": level,
            "device": device,
        }
    except Exception as error:
        return {"ok": False, "category": "PROVIDER_ERROR", "error": f"DINOv3 view check failed: {error}"}


if __name__ == "__main__":
    try:
        write_result(run(read_request()))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        write_result({"ok": False, "category": "WORKER_REQUEST", "error": str(error)})
