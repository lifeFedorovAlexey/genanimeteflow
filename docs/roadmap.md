# Character Factory delivery roadmap

Each checked item must have working code, automated coverage where practical, a real local run, and a small Git commit. An unavailable external model is recorded as a concrete capability constraint; it is never represented as a successful generation.

## Product UX acceptance

- [ ] Implement the user-approved [workspace design brief](ui-design-brief.md): input/settings on the left, dominant 3D viewport in the center, real result gallery on the right, without billing or promotional UI. This is an acceptance requirement, not a claim that the current UI matches it.
- [ ] The interface must be understandable without a manual: each screen makes the next action, current progress, blocking reason and successful result visually obvious. Technical status text is secondary; controls use real user actions instead of generic labels such as `Run`.

## Foundation

- [x] Repository layout, Python API and React/TypeScript web app
- [x] Persistent job manifests with atomic writes
- [x] Live hardware diagnostics and `hardware_profile.json`
- [x] Single-GPU serialization boundary
- [x] Reference upload, original preservation and real preprocessing
- [x] Structured stage logs and SSE job events
- [x] GLB mesh validation and embedded texture extraction
- [x] Motion catalog registration with license metadata, SHA-256 and GLB clip inspection
- [x] Deterministic locomotion/action graph evaluator with equipment-aware clip selection
- [x] Foundation tests and production web build
- [x] Windows and WSL setup scripts use the project virtual environment and report Blender availability

## Pipeline stages

- [x] Implement SPAR3D provider subprocess protocol and generated-mesh persistence (runtime requires official checkout and weights)
- [x] Pin and install a real local single-image geometry worker; expose model download/integrity checks
- [x] Implement real textured output and full PBR material validation (embedded extraction is implemented)
- [x] Implement Blender retopology worker with GLB validation (UV-preserving quad mode remains gated)
- [x] Implement UniRig worker bridge, official skeleton/skin inference and skin-weight validation (runtime requires official checkout, checkpoint and WSL CUDA)
- [x] Implement licensed motion library installation, normalization and catalog validation (UAL2 Standard CC0 fixture: 43 clips, real local install and catalog scan)
- [x] Add real Blender canonical-bone retarget worker with bake and GLB roundtrip validation (runtime requires Blender and installed source clips)
- [x] Connect installed motion clips to job selection, catalog validation and the motions stage
- [x] Connect graph evaluation endpoint to normalized Blender actions and Unit Tester state changes (upper-body bone-mask playback and source-gated additive contract are implemented; full acceptance clips remain)
- [ ] Implement retargeting and the canonical animation graph (canonical retarget worker is real and smoke-tested; full graph blending, locomotion transitions and acceptance clips remain)
- [x] Implement equipment, clothing, sockets and IK validation (real acceptance run: Utility Vest + CC0 Lightning Rifle, one socket, four IK targets/constraints)
- [x] Add validated local equipment manifest/catalog registration with license-independent provenance and socket/grip metadata
- [x] Add Blender rigid-equipment socket attachment stage with output and skeleton validation (skinned clothing and IK remain separate stages)
- [x] Load validated GLB assets in Unit Tester with embedded clip playback, WASD movement states and wireframe/skeleton debug toggles
- [x] Implement GLB/FBX export worker and manifest roundtrip validation (runtime requires Blender and selected normalized actions)
- [ ] Harden recovery, cancellation, cache cleanup, security and full acceptance test (recovery/cancellation/cache cleanup, acceptance verifier and path-boundary tests are implemented; end-to-end fresh-run sign-off remains)

## Commit convention

Use focused commits such as `foundation: persistent jobs and diagnostics`, `geometry: spar3d worker protocol`, and `export: glb roundtrip validation`. Do not commit generated `.venv`, `node_modules`, job inputs, or model weights.
