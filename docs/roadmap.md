# Character Factory delivery roadmap

Each checked item must have working code, automated coverage where practical, a real local run, and a small Git commit. An unavailable external model is recorded as a concrete capability constraint; it is never represented as a successful generation.

## Foundation

- [x] Repository layout, Python API and React/TypeScript web app
- [x] Persistent job manifests with atomic writes
- [x] Live hardware diagnostics and `hardware_profile.json`
- [x] Single-GPU serialization boundary
- [x] Reference upload, original preservation and real preprocessing
- [x] Structured stage logs and SSE job events
- [x] Foundation tests and production web build

## Pipeline stages

- [ ] Pin and install a real local single-image geometry worker; expose model download/integrity checks
- [ ] Implement SPAR3D provider subprocess protocol and generated-mesh persistence
- [ ] Implement real textured output and PBR asset validation
- [ ] Implement Blender retopology/UV worker with roundtrip checks
- [ ] Implement UniRig worker, canonical mapping and skin-weight validation
- [ ] Implement licensed motion library installation, normalization and catalog validation
- [ ] Implement retargeting and the canonical animation graph
- [ ] Implement equipment, clothing, sockets and IK validation
- [ ] Load validated GLB assets in Unit Tester and add controls/debug views
- [ ] Implement GLB/FBX export and manifest roundtrip validation
- [ ] Harden recovery, cancellation, cache cleanup, security and full acceptance test

## Commit convention

Use focused commits such as `foundation: persistent jobs and diagnostics`, `geometry: spar3d worker protocol`, and `export: glb roundtrip validation`. Do not commit generated `.venv`, `node_modules`, job inputs, or model weights.
