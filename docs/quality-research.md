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

The Pixal3D candidate remains useful as a quality comparator. Meta has granted
the user's official DINOv3 gating request; a local token check now returns the
user account and HTTP 200 for the gated model page. The DINOv3 weights are still
not downloaded because Pixal3D is a comparator, not the primary production path.
Do not silently substitute an unofficial mirror for a gated official checkpoint.

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

The official Hunyuan3D-2mv checkpoint is now downloaded to the external model
store and passed a real CUDA load preflight on the RTX 4070. The official
single-view Hunyuan3D-2 checkpoint also passed a real CUDA load preflight with
Torch 2.8/cu128 on the same GPU. The Hunyuan Paint Turbo UNet and remaining
Delight/image-encoder weights are staged in the same store; these files are
intentionally excluded from Git. Paint is now verified by a local load and a
real textured mesh run; the weights remain excluded from Git.

## First complete local smoke run

Job `c3454980-4591-42b9-af37-ec01d5f92977` ran the official single-view path on
the user's FRONT reference. Shape generation completed in 94.4 seconds with a
validated GLB of 407,263 vertices and 814,546 triangles; peak measured VRAM was
8.67 GiB. Hunyuan Paint then completed in 628.3 seconds and produced a
validated textured GLB with 814,546 triangles, one material and one embedded
texture. The output is a smoke-run proof of the local pipeline, not a claim of
Tripo-level visual equivalence; a controlled multi-view benchmark is still
required for that claim.

## UniRig local smoke run

The official UniRig skeleton and skin checkpoints are available through the
user's granted Hugging Face access and run in WSL with CUDA `12.8` PyTorch and
`spconv-cu124`. The Windows bridge extracts the source GLB through Blender,
runs the official skeleton and skin predictors, transfers the 32k sampled skin
predictions back to the original mesh with KD-tree alignment, and exports a
textured rigged GLB. A full worker run on the Hunyuan Paint output completed
successfully: `42` joints including the canonical root, `2,439,662` influenced
vertices, and a valid non-empty GLB. The exporter now maps the real UniRig
humanoid parent graph to Mixamo-compatible canonical names and rejects a
non-humanoid graph instead of silently producing an unusable rig.

## Motion-library and retarget smoke run

The free Standard distribution of Quaternius Universal Animation Library 2 was
installed through `MotionLibrary` after checking its embedded `CC0 1.0
Universal` license. The local GLB contains `43` named actions and `65`
humanoid bones, including idle, walk, jump, melee and sword clips. The real
Blender retarget worker mapped its `pelvis/thigh_l/calf_l` naming to the
canonical UniRig output, baked `Idle_No_Loop`, removed the other source
actions, and exported a `142,578,472`-byte textured GLB. Final validation passed
with one animation, one skin, one embedded texture, `2,440,265` influenced
vertices and the complete canonical mapping. This proves one real clip from
library registration through target-rig retargeting; locomotion graph blending,
the remaining acceptance clips and visual deformation review remain open.

## End-to-end rig, motion and export job

Job `c3454980-4591-42b9-af37-ec01d5f92977` was then driven through the actual
API stages, not only direct worker calls. Retopology produced the rig input,
UniRig returned a canonical validated character, and the motions stage
normalized `Idle_No_Loop`, `Zombie_Walk_Fwd_Loop`, `NinjaJump_Start` and
`Melee_Hook`; every output passed GLB and canonical-rig validation. The export
worker assembled the four separate normalized actions through Blender NLA
tracks, and the final `unit.glb` roundtrip contains exactly four animations,
one skin, one embedded texture and a valid canonical rig. `unit.fbx` and the
unit manifest were also created. The graph endpoint selected idle, walk, jump
and attack states against those real actions. This is the first complete local
animation/export proof; it is not yet a claim that the deformations visually
match Mixamo on every body shape.

## Multiview geometry smoke run

On 2026-09-22 the official Hunyuan3D-2mv worker was run on three distinct
upstream sample images (`front`, `left`, `back`) with the production BALANCED
settings (`50` steps, octree `384`, `num_chunks=20000`, low-VRAM mode). The
worker completed on the RTX 4070 in `95.7 s`, returned
`HunyuanMultiviewProvider`, and reported `ignored_views=[]`. The generated
GLB passed the repository validator with `325,447` vertices and `650,884`
faces. It is a geometry-only provider smoke proof: it has no UVs, materials,
rig or animation until the normal downstream stages run. It does not replace
the required acceptance run with the user's four real reference images.

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
