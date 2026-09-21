from __future__ import annotations

import torch
from torch import nn


class MHA(nn.Module):
    """State-dict-compatible cross-attention fallback for flash_attn.modules.mha."""

    def __init__(self, embed_dim: int, num_heads: int, cross_attn: bool = False, **_: object) -> None:
        super().__init__()
        if embed_dim % num_heads:
            raise ValueError("embed_dim must be divisible by num_heads")
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.cross_attn = cross_attn
        self.head_dim = embed_dim // num_heads
        self.Wq = nn.Linear(embed_dim, embed_dim)
        self.Wkv = nn.Linear(embed_dim, 2 * embed_dim)
        self.out_proj = nn.Linear(embed_dim, embed_dim)

    def forward(self, x: torch.Tensor, x_kv: torch.Tensor | None = None, **_: object) -> torch.Tensor:
        key_value = x if x_kv is None else x_kv
        batch, query_len, _ = x.shape
        key_len = key_value.shape[1]
        query = self.Wq(x).view(batch, query_len, self.num_heads, self.head_dim).transpose(1, 2)
        key, value = self.Wkv(key_value).chunk(2, dim=-1)
        key = key.view(batch, key_len, self.num_heads, self.head_dim).transpose(1, 2)
        value = value.view(batch, key_len, self.num_heads, self.head_dim).transpose(1, 2)
        attended = torch.nn.functional.scaled_dot_product_attention(query, key, value)
        attended = attended.transpose(1, 2).reshape(batch, query_len, self.embed_dim)
        return self.out_proj(attended)
