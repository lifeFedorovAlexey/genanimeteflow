from __future__ import annotations

import torch
from torch import Tensor


def flash_attn_varlen_qkvpacked_func(
    qkv: Tensor,
    cu_seqlens: Tensor,
    max_seqlen: int,
    dropout_p: float = 0.0,
    softmax_scale: float | None = None,
    **_: object,
) -> Tensor:
    """Portable fallback for UniRig's packed variable-length attention call."""
    outputs: list[Tensor] = []
    for start, end in zip(cu_seqlens[:-1].tolist(), cu_seqlens[1:].tolist()):
        if end <= start:
            continue
        packed = qkv[start:end]
        query, key, value = packed.unbind(dim=1)
        query = query.transpose(0, 1)
        key = key.transpose(0, 1)
        value = value.transpose(0, 1)
        scale = softmax_scale or query.shape[-1] ** -0.5
        scores = (query @ key.transpose(-2, -1)) * scale
        weights = scores.softmax(dim=-1)
        if dropout_p:
            weights = torch.nn.functional.dropout(weights, p=dropout_p, training=True)
        outputs.append((weights @ value).transpose(0, 1))
    return torch.cat(outputs, dim=0) if outputs else qkv.new_empty((0, qkv.shape[3], qkv.shape[4]))


from .modules.mha import MHA

__all__ = ["MHA", "flash_attn_varlen_qkvpacked_func"]
