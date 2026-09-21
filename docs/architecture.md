# Character Factory architecture

The local application is split into a React/TypeScript browser UI and a FastAPI orchestration service. Jobs are persisted under `jobs/<uuid>/job.json` with source references, processed references, logs and stage-specific folders. API writes use atomic replacement so an interrupted update cannot leave a half-written manifest.

GPU work is serialized through `SingleGpuQueue`. Heavy ML stages are intentionally reported as unavailable until their pinned worker and model weights are installed; the UI never presents an unavailable provider as a successful generation result.

The first working stage is reference intake and preprocessing. It accepts front/left/back/right image slots, preserves originals, produces normalized transparent PNGs, computes foreground diagnostics and persists the report. Subsequent workers plug into the same manifest and stage lifecycle.
