"""Run official UniRig inference while keeping Blender export in its own bridge."""
from __future__ import annotations

import argparse
import runpy
import sys
import types
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--npz-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # The official runner imports bpy for its exporter even when inference is
    # executed in WSL. The actual export is performed later by Blender 5.x.
    sys.modules.setdefault("bpy", types.ModuleType("bpy"))

    import torch

    original_torch_load = torch.load

    def trusted_torch_load(*load_args, **load_kwargs):
        # The official checkpoint contains python-box metadata and is fetched
        # from the trusted VAST-AI repository; Lightning passes True explicitly
        # on recent PyTorch, so set the compatibility mode unconditionally.
        load_kwargs["weights_only"] = False
        return original_torch_load(*load_args, **load_kwargs)

    torch.load = trusted_torch_load

    from transformers import AutoConfig

    original_from_pretrained = AutoConfig.from_pretrained.__func__

    def eager_config(cls, *config_args, **config_kwargs):
        config = original_from_pretrained(cls, *config_args, **config_kwargs)
        config._attn_implementation = "eager"
        config.attn_implementation = "eager"
        return config

    AutoConfig.from_pretrained = classmethod(eager_config)

    from src.data.raw_data import RawData

    def save_prediction(self: RawData, path: str, *_, **__) -> None:
        self.save(str(Path(path).with_suffix(".npz")))

    RawData.export_fbx = save_prediction
    sys.argv = [
        "run.py",
        f"--task={args.task}",
        f"--seed={args.seed}",
        f"--input={args.input}",
        f"--output={args.output}",
        f"--npz_dir={args.npz_dir}",
    ]
    runpy.run_module("run", run_name="__main__")


if __name__ == "__main__":
    main()
