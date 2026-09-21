# Quality investigation — 2026-09-21

## Decision and evidence boundary

Target: a completely local, animation-ready character whose visible quality and
deformations are not inferior to the user's Tripo + Mixamo comparison. Passing
mesh validation alone does not establish that quality. No percentage-equivalence
claim is currently supported. No new candidate has yet generated this character locally.

The first Tencent candidate is **Hunyuan3D-2mv + Paint**, with audited CPU
offloading. It directly addresses the original spec's multiview path: the official
pipeline accepts named FRONT/LEFT/BACK images and produces one mesh. Do not default
to mini/turbo merely because they are easier to run. Provider selection remains
provisional until same-input comparisons exist.

The higher-fidelity **Hunyuan3D-2.1** shape/PBR pair is an experimental MAX path.
Tencent's model card reports roughly 10 GB for shape, 21 GB for texture and 29 GB
for both, so the RTX 4070 cannot run the full pair concurrently. Sequential CPU
offload may make it possible, but this is an explicit hardware experiment, not a
guaranteed 12 GB mode. **Hunyuan3D-Omni** is a shape/control model (including pose
control), not a replacement for texturing, rigging or animation.

The Pixal3D candidate remains useful as a quality comparator. Its official DINOv3
access check returned HTTP 403 with the saved account on 2026-09-21. Do not
download its large bundle before that prerequisite is satisfied; do not silently
substitute an unofficial mirror for a gated official checkpoint.

## Actual machine

Read-only local diagnostics found Ryzen 9 7900X, RTX 4070 (12,282 MiB), driver
591.86, and 67,756,347,392 bytes physical RAM (~63.1 GiB). This supersedes earlier
unverified 5900/32 GB descriptions, without assuming upgraded hardware.
At inspection D: had ~49.2 GiB free and C: ~35.4 GiB. WSL Ubuntu is available
but sees ~30 GiB RAM / 8 GiB swap and has no `nvcc` in PATH. Disk and memory must
be rechecked before installation, including actual Windows capacity behind WSL.

## Candidates

| Candidate | Why evaluate | Remaining proof / constraints |
| --- | --- | --- |
| [Pixal3D](https://github.com/TencentARC/Pixal3D) | Pixel-aligned conditioning, geometry and PBR; native on-demand loading | Author CLI estimates ~10–12 GB in low-VRAM mode, not a measured bound on this PC. CUDA extensions and auxiliary weights required. Multiview uses separate weights and camera transforms, not arbitrary labels. |
| [TRELLIS.2](https://github.com/microsoft/TRELLIS.2) | Detailed shape and spatial PBR output | Upstream advertises 24 GB; [community implementation](https://github.com/visualbruno/ComfyUI-Trellis2) offers memory optimizations. Need verify 12 GB execution and any quantization loss; also uses DINOv3. |
| [Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2) | Official multiview shape plus separate texture pipeline | [2GP](https://github.com/deepbeepmeep/Hunyuan3D-2GP) provides offload profiles targeting 9/6 GB. Those are author targets, not local results; audit source and test full mv rather than mini. |
| [Hunyuan3D-2.1](https://huggingface.co/tencent/Hunyuan3D-2.1) | Tencent's newer higher-fidelity shape and PBR pair; strongest Tencent quality candidate | Tencent reports ~10 GB shape / ~21 GB texture / ~29 GB together. Shape may fit with reserve; Paint needs sequential offload or a downgrade. No local result yet. |
| [Hunyuan3D-Omni](https://huggingface.co/tencent/Hunyuan3D-Omni) | Shape generation with pose, point, voxel and bounding-box controls; useful for controlled humanoid shape | 3.3B shape model, Tencent reports ~10 GB generation. It is not a textured or rigged output and has no multiview image interface documented as the primary path. |
| [Hunyuan3D-Part](https://huggingface.co/tencent/Hunyuan3D-Part) | Part segmentation/decomposition after generation; useful for clothing/equipment separation | It is downstream of a mesh and the released X-Part is a light version; not the geometry generator itself. |
| [TripoSG](https://github.com/VAST-AI-Research/TripoSG) | Official image-to-shape candidate advertising 8 GB minimum | Not the commercial Tripo service and not a complete textured character pipeline; separate texturing still required. |
| [UniRig](https://github.com/VAST-AI-Research/UniRig) | Required by original spec: general skeleton and skinning | Must measure humanoid mapping and deformation quality; broader object support does not prove superiority to Mixamo. |
| [Make-It-Animatable](https://github.com/jasongzy/Make-It-Animatable) | Humanoid-specific rigging comparator; published official inference and weights | Evaluate skeleton, fingers and skinning on generated mesh. No local VRAM/time or quality result yet; don't use training hardware requirements as inference requirements. |

[TripoSF](https://github.com/VAST-AI-Research/TripoSF) is mesh reconstruction via
a VAE, not a standalone image-to-3D substitute. Raising SPAR3D texture resolution
is likewise not a replacement for improving missing geometry.

## Pinned research snapshots

These pins identify inspected candidates; they do **not** mean installed/working.

- Pixal3D code: `f7cf38429b0bd264f1995f0f8743a88b1c728b94` (actual default branch `master`).
- Pixal3D HF weights: `b0cb2e1b794cab9aa0ac38a95d794a4d9337437f`.
- Official `facebook/dinov3-vitl16-pretrain-lvd1689m`: `ea8dc2863c51be0a264bab82070e3e8836b02d51`.
- TRELLIS.2 code: `75fbf0183001ed9876c8dbb35de6b68552ee08bd`.
- TripoSG code: `fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c`.
- Hunyuan3D-2GP code: `f2456e036a86a4b1d9f58e2379fe7ab0fe9b68b0`.
- Official Hunyuan3D-2mv weights: `3a761b539b29fe4ff64714813aa9560fd66f5de0`.
- Official Hunyuan3D-2.1 model card was inspected; its published memory figures are recorded above.

Pixal3D's seven single-view checkpoint files total about 24.05 GB decimal,
excluding auxiliary models, dependencies and build space. Whole-repository weight
downloads would also fetch separate multiview checkpoints. Enumerate selected
files, sizes, immutable revisions, licenses and destination before any download.
Keep each worker environment isolated from the working SPAR3D installation.

## Current SPAR3D diagnosis

Local job `399692df-1073-497e-abab-47d1819716e9`, latest T-pose input:

- Original geometry and retopology previews show similar coarse forms; retopology
  alone is not the explanation for the visual defects.
- `previews/diagnostic-albedo.png` retains eye/color detail better than lit PBR.
  `previews/diagnostic-clay.png` still shows coarse face, hands and armor geometry.
- Inspected GLB uses global metallic ~0.439 and roughness ~0.466, including skin
  and hair. Material response exaggerates defects but does not explain all of them.
- Reference replacement previously left old downstream results marked READY;
  viewer URLs were also unchanged on reruns. Both confound visual comparisons.
- Official SPAR3D already preserves existing transparent input during background
  removal. A claimed unconditional double-removal problem was not substantiated.
- Its low-VRAM path moves modules between CPU/GPU. No intrinsic quality loss from
  that switch has been demonstrated; earlier runs were not controlled seed A/Bs.

## Benchmark and acceptance procedure

1. Preserve original/processed input hashes, provider code/weight revisions,
   preprocessing, seed, settings and actual views. Never duplicate FRONT as BACK.
2. Run seeds 42, 43 and 44 for supported stochastic providers. Save every result;
   disclose failures and do not cherry-pick one attractive run as general quality.
3. Record wall time, total device VRAM baseline/peak/after, process RAM peak and
   settings. Run one GPU worker at a time; verify process exit and memory release.
4. Render front/side/back in materials, unlit base color and neutral clay using
   consistent framing/lighting. Compare raw mesh, retopology and exported reload.
5. Inspect face/eyes and resemblance, head/body proportions, fingers, armor edges,
   cape separation, seams, unseen surfaces and material maps. A texture cannot
   compensate for missing geometry. Unsupported PBR maps must remain absent.
6. Inspect rig and weights, then idle/walk/run/jump/attack: shoulders, elbows,
   knees, fingers, cape, volume collapse, intersections and foot sliding. Include
   equipment and clothing/IK tests from the full original acceptance scenario.
7. Compare actual Tripo and Mixamo outputs from the same reference and comparable
   settings before asserting parity. Such baseline assets are not yet available.
   A screenshot or paper benchmark is insufficient for this claim.

Reject a candidate as the final default if it fails the character quality target,
even if it fits memory and passes file validation. Maintain the complete original
TЗ: alternative providers add options; they do not erase rigging, multiview,
retopology/UV, animation graph, equipment/clothing, IK or export obligations.
