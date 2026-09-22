import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Capabilities, EquipmentCatalog, Hardware, Job, MotionCatalog, StageRecord, ViewName } from "./api";
import Viewport from "./Viewport";

const views: Array<{ id: ViewName; label: string; required: boolean }> = [
  { id: "front", label: "FRONT", required: true }, { id: "left", label: "LEFT", required: false }, { id: "back", label: "BACK", required: false }, { id: "right", label: "RIGHT", required: false },
];

const stageOrder = ["references", "geometry", "textures", "retopology", "rig", "clothing", "equipment", "ik", "motions", "export"];
const stageMeta: Record<string, { label: string; action: string; icon: string }> = {
  references: { label: "Изображения", action: "Обработать", icon: "01" },
  geometry: { label: "3D‑форма", action: "Создать форму", icon: "02" },
  textures: { label: "Материалы", action: "Нанести материалы", icon: "03" },
  retopology: { label: "Игровая сетка", action: "Оптимизировать сетку", icon: "04" },
  rig: { label: "Скелет", action: "Собрать скелет", icon: "05" },
  clothing: { label: "Одежда", action: "Перенести одежду", icon: "06" },
  equipment: { label: "Экипировка", action: "Подключить экипировку", icon: "07" },
  ik: { label: "IK", action: "Подготовить IK", icon: "08" },
  motions: { label: "Анимации", action: "Нормализовать движения", icon: "09" },
  export: { label: "Экспорт", action: "Экспортировать юнит", icon: "10" },
};

function statusLabel(status?: string): string {
  if (status === "READY") return "Готово";
  if (status === "RUNNING") return "В работе";
  if (status === "FAILED" || status === "FAILED_OOM") return "Нужно внимание";
  if (status === "CANCELLED") return "Остановлено";
  return "Ожидает";
}

function optimisticRunning(job: Job, stage: string): Job {
  const record = job.stages[stage];
  return { ...job, status: "RUNNING", stages: { ...job.stages, [stage]: { ...(record as StageRecord), status: "RUNNING" } } };
}

function canRunStage(job: Job, stage: string, capabilities?: Capabilities): boolean {
  if (!capabilities?.stages[stage]?.available) return false;
  if (stage === "references") return Boolean(job.references.front);
  if (stage === "geometry") return job.stages.references?.status === "READY";
  if (stage === "textures") return job.stages.geometry?.status === "READY";
  if (stage === "retopology") return job.stages.textures?.status === "READY";
  if (stage === "rig") return job.stages.retopology?.status === "READY";
  if (stage === "equipment") return job.stages.rig?.status === "READY" && job.equipment_assets.length > 0;
  if (stage === "clothing") return job.stages.rig?.status === "READY" && job.clothing_assets.length > 0;
  if (stage === "ik") return job.stages.rig?.status === "READY";
  if (stage === "motions") return job.stages.rig?.status === "READY" && job.motion_clips.length > 0;
  if (stage === "export") return job.stages.motions?.status === "READY" && job.export_actions.length > 0;
  return false;
}

function blockedReason(job: Job, stage: string, capabilities?: Capabilities): string {
  const record = job.stages[stage];
  if (stage === "equipment" && job.equipment_assets.length === 0) return "Можно пропустить: оставьте пустым для персонажа без экипировки";
  if (stage === "clothing" && job.clothing_assets.length === 0) return "Можно пропустить: добавьте одежду, если она нужна";
  if (record?.error_message) return record.error_message;
  if (!capabilities?.stages[stage]?.available) return capabilities?.stages[stage]?.reason ?? "Инструмент недоступен на этом компьютере";
  if (stage === "references" && !job.references.front) return "Сначала добавьте изображение FRONT";
  if (stage === "geometry" && job.stages.references?.status !== "READY") return "Сначала обработайте изображения";
  if (stage === "textures" && job.stages.geometry?.status !== "READY") return "Сначала создайте 3D‑форму";
  if (stage === "retopology" && job.stages.textures?.status !== "READY") return "Сначала нанесите материалы";
  if (stage === "rig" && job.stages.retopology?.status !== "READY") return "Сначала оптимизируйте сетку";
  if (stage === "equipment" && job.equipment_assets.length === 0) return "Можно пропустить: зарегистрируйте экипировку при необходимости";
  if (stage === "clothing" && job.clothing_assets.length === 0) return "Можно пропустить: добавьте одежду при необходимости";
  if (stage === "equipment" && job.stages.rig?.status !== "READY") return "Сначала соберите скелет";
  if (stage === "ik" && job.stages.rig?.status !== "READY") return "Сначала соберите скелет";
  if (stage === "motions" && job.motion_clips.length === 0) return "Сначала выберите движения в библиотеке";
  if (stage === "motions" && job.stages.rig?.status !== "READY") return "Сначала соберите скелет";
  if (stage === "export" && job.export_actions.length === 0) return "Выберите хотя бы одну анимацию для экспорта";
  if (stage === "export" && job.stages.motions?.status !== "READY") return "Сначала нормализуйте движения";
  return "Ожидает завершения предыдущего шага";
}

function nextStep(job: Job, capabilities?: Capabilities): { title: string; body: string; stage?: string; action?: string; tone: "action" | "blocked" | "done" } {
  if (!job.references.front) return { title: "Добавьте FRONT персонажа", body: "Перетащите изображение персонажа в полный рост в первый слот.", stage: "references", action: "Добавить FRONT", tone: "action" };
  const failed = stageOrder.map(stage => ({ stage, record: job.stages[stage] })).find(item => item.record?.status === "FAILED" || item.record?.status === "FAILED_OOM");
  if (failed) return { title: `${stageMeta[failed.stage].label}: нужно внимание`, body: failed.record.error_message ?? "Откройте детали шага и запустите его ещё раз.", stage: failed.stage, action: "Повторить", tone: "blocked" };
  const running = stageOrder.find(stage => job.stages[stage]?.status === "RUNNING");
  if (running) return { title: `${stageMeta[running].label} выполняется`, body: "Результат появится здесь автоматически после завершения.", tone: "action" };
  if (job.stages.export?.status === "READY") return { title: "Юнит готов", body: "Проверенный GLB доступен в галерее результатов.", tone: "done" };
  const pending = stageOrder.find(stage => {
    const record = job.stages[stage];
    if (record?.status === "READY") return false;
    if (stage === "equipment" && job.equipment_assets.length === 0) return false;
    if (stage === "clothing" && job.clothing_assets.length === 0) return false;
    return true;
  });
  if (pending) {
    const canRun = canRunStage(job, pending, capabilities);
    return { title: canRun ? stageMeta[pending].action : `Подготовьте: ${stageMeta[pending].label.toLowerCase()}`, body: blockedReason(job, pending, capabilities), stage: canRun ? pending : undefined, action: canRun ? stageMeta[pending].action : undefined, tone: canRun ? "action" : "blocked" };
  }
  return { title: "Юнит готов", body: "Все доступные шаги успешно завершены.", tone: "done" };
}

function App() {
  const [hardware, setHardware] = useState<Hardware>();
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [motionCatalog, setMotionCatalog] = useState<MotionCatalog>();
  const [equipmentCatalog, setEquipmentCatalog] = useState<EquipmentCatalog>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cacheItems, setCacheItems] = useState<Array<{ job_id: string; cache_bytes: number; cleanable: boolean; reason: string }>>([]);
  const [active, setActive] = useState<Job>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [hardwareResult, capabilitiesResult, jobsResult, motionsResult, equipmentResult, cacheResult] = await Promise.allSettled([api.hardware(), api.capabilities(), api.jobs(), api.motions(), api.equipment(), api.cache()]);
    if (hardwareResult.status === "fulfilled") setHardware(hardwareResult.value);
    if (capabilitiesResult.status === "fulfilled") setCapabilities(capabilitiesResult.value);
    if (jobsResult.status === "fulfilled") {
      setJobs(jobsResult.value);
      setActive(current => current ? jobsResult.value.find(job => job.job_id === current.job_id) ?? current : jobsResult.value[0]);
    }
    if (motionsResult.status === "fulfilled") setMotionCatalog(motionsResult.value);
    if (equipmentResult.status === "fulfilled") setEquipmentCatalog(equipmentResult.value);
    if (cacheResult.status === "fulfilled") setCacheItems(cacheResult.value.items);
    const criticalFailure = [capabilitiesResult, jobsResult, cacheResult].find(result => result.status === "rejected");
    if (criticalFailure?.status === "rejected") setError(criticalFailure.reason instanceof Error ? criticalFailure.reason.message : String(criticalFailure.reason));
    else setError("");
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => { void api.jobs().then(list => { setJobs(list); const next = list.find(job => job.job_id === active.job_id); if (next) setActive(next); }).catch(() => undefined); }, 1000); return () => window.clearInterval(timer); }, [active?.job_id]);

  const create = async () => { setBusy(true); setError(""); try { const job = await api.createJob({ name: "Character Unit", profile: hardware?.recommendation ?? "BALANCED", resolution: 512, requested_provider: "AUTO" }); setActive(job); setJobs(list => [job, ...list]); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const upload = async (view: ViewName, file?: File) => { if (!active || !file) return; setBusy(true); setError(""); try { const job = await api.upload(active.job_id, view, file); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const runStage = async (stage: string) => { if (!active) return; setBusy(true); setError(""); setActive(optimisticRunning(active, stage)); try { await api.runStage(active.job_id, stage); } catch (err) { setError(err instanceof Error ? err.message : String(err)); void refresh(); } finally { setBusy(false); } };
  const cancelStage = async (stage: string) => { if (!active) return; setBusy(true); setError(""); try { await api.cancelStage(active.job_id, stage); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleMotion = async (clipId: string) => { if (!active) return; setBusy(true); setError(""); const clips = active.motion_clips.includes(clipId) ? active.motion_clips.filter(id => id !== clipId) : [...active.motion_clips, clipId]; try { const job = await api.setMotionSelection(active.job_id, clips); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleExportAction = async (action: string) => { if (!active) return; setBusy(true); setError(""); const actions = active.export_actions.includes(action) ? active.export_actions.filter(item => item !== action) : [...active.export_actions, action]; try { const job = await api.setExportSelection(active.job_id, actions); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleEquipment = async (assetId: string) => { if (!active) return; setBusy(true); setError(""); const assets = active.equipment_assets.includes(assetId) ? active.equipment_assets.filter(id => id !== assetId) : [...active.equipment_assets, assetId]; try { const job = await api.setEquipmentSelection(active.job_id, assets); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleClothing = async (assetId: string) => { if (!active) return; setBusy(true); setError(""); const assets = active.clothing_assets.includes(assetId) ? active.clothing_assets.filter(id => id !== assetId) : [...active.clothing_assets, assetId]; try { const job = await api.setClothingSelection(active.job_id, assets); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const activeStage = active?.stages.references;
  const gpu = hardware?.gpu.gpus[0];
  const readyViews = useMemo(() => Object.values(active?.references ?? {}).filter(slot => slot.quality?.level !== "ERROR").length, [active]);
  const assetStage = ["export", "ik", "equipment", "clothing", "rig", "textures", "retopology", "geometry"].map(stage => active?.stages[stage]).find(stage => stage?.status === "READY");
  const assetPath = typeof assetStage?.result.glb_path === "string"
    ? assetStage.result.glb_path
    : typeof assetStage?.result.mesh_path === "string"
      ? assetStage.result.mesh_path
      : typeof assetStage?.result.source_mesh === "string" ? assetStage.result.source_mesh : undefined;
  // useGLTF caches by URL. A completed rerun must load the new GLB, while
  // unrelated polling/other stage changes must not reset the viewport.
  const assetUrl = active && assetPath ? `/api/jobs/${active.job_id}/files/${assetPath.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/")}?v=${encodeURIComponent(assetStage?.finished_at ?? "legacy")}` : undefined;
  const finalGlbPath = active?.stages.export?.status === "READY" && typeof active.stages.export.result.glb_path === "string" ? active.stages.export.result.glb_path : undefined;
  const finalGlbUrl = active && finalGlbPath ? `/api/jobs/${active.job_id}/files/${finalGlbPath.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/")}` : undefined;
  const normalizedClips = useMemo(() => { const raw = active?.stages.motions?.result.clips; return (Array.isArray(raw) ? raw : []) as Array<{ clip_id: string; action: string; category?: string; worker?: { normalized_action?: string } }>; }, [active]);
  const equipmentType = useMemo(() => {
    const selected = equipmentCatalog?.assets.find(asset => active?.equipment_assets.includes(asset.id));
    const tags = (selected?.tags ?? []).map(tag => tag.toLowerCase());
    return ["rifle", "pistol", "sword", "shield", "staff", "bow"].find(type => tags.includes(type)) ?? null;
  }, [active?.equipment_assets, equipmentCatalog]);
  const resultJobs = useMemo(() => jobs.filter(job => job.stages.export?.status === "READY").slice(0, 20), [jobs]);
  const cleanableCache = useMemo(() => cacheItems.filter(item => item.cleanable && item.cache_bytes > 0), [cacheItems]);
  const next = active ? nextStep(active, capabilities) : undefined;

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-mark">CF</div><div><h1>Character Factory</h1><p>Build a playable character, one clear step at a time</p></div></div><div className="top-actions"><span className="status-dot" /> LOCAL ONLY {cleanableCache.length > 0 && <button className="secondary" onClick={() => { if (window.confirm(`Clear intermediate files for ${cleanableCache.length} abandoned unit(s)? References and exports are protected.`)) void api.cleanCache(cleanableCache.map(item => item.job_id)).then(() => void refresh()).catch(err => setError(err instanceof Error ? err.message : String(err))); }}>Clean cache · {cleanableCache.length}</button>} <button className="secondary" onClick={() => void refresh()}>Refresh</button></div></header>
    <main className="workspace"><aside className="sidebar"><div className="section-head"><span>UNITS</span><button className="icon-button" onClick={() => void create()} disabled={busy} aria-label="Create a new unit" title="Create a new unit">＋</button></div>{jobs.length === 0 && <p className="muted">Create your first unit</p>}{jobs.map(job => <button key={job.job_id} className={`job-row ${active?.job_id === job.job_id ? "selected" : ""}`} onClick={() => setActive(job)}><span className={`job-icon ${job.status === "RUNNING" ? "pulse" : ""}`}>{job.status === "READY" ? "✓" : "◇"}</span><span><strong>{job.job_id.slice(0, 8)}</strong><small>{job.status === "RUNNING" ? "Working" : job.status === "READY" ? "Ready" : "In progress"}</small></span></button>)}<div className="sidebar-bottom"><span>LOCAL WORKSPACE</span><strong>Nothing leaves this computer</strong></div></aside>
      <section className="content"><div className="content-title"><div><div className="eyebrow">{active ? `UNIT ${active.job_id.slice(0, 8)}` : "WELCOME"}</div><h2>{active ? "Build your character" : "Character Factory"}</h2></div><button className="primary" onClick={() => void create()} disabled={busy}>＋ New unit</button></div>{error && <div className="error-banner"><strong>Something needs attention</strong><span>{error}</span></div>}
        {!active ? <div className="welcome"><h3>Start with one character image</h3><p>We will guide the unit through shape, skeleton, motion and export.</p><button className="primary" onClick={() => void create()}>Create unit</button></div> : <>
          {next && <div className={`next-card ${next.tone}`}><div className="next-icon">{next.tone === "done" ? "✓" : next.tone === "blocked" ? "!" : "→"}</div><div className="next-copy"><span className="eyebrow">NEXT STEP</span><h3>{next.title}</h3><p>{next.body}</p></div>{next.stage && <button className="primary" onClick={() => void runStage(next.stage!)} disabled={busy}>{next.action}</button>}</div>}
          <div className="dashboard-grid"><div className="panel references"><div className="panel-header"><div><span className="eyebrow">START HERE</span><h3>Character images</h3></div><span className={`pill ${readyViews ? "good" : "neutral"}`}>{readyViews}/4</span></div><p className="panel-note">FRONT starts the pipeline. Add the other views when you have them.</p><div className="reference-grid">{views.map(view => { const slot = active.references[view.id]; return <label key={view.id} className={`drop-slot ${slot ? "has-file" : ""}`}><input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void upload(view.id, event.target.files?.[0])} /><span className="slot-label">{view.label}{view.required && <sup>*</sup>}</span>{slot ? <><span className="slot-check">✓</span><small>{slot.quality?.level ?? "Ready to process"}</small></> : <span className="upload-hint">Drop or browse</span>}</label>; })}</div><div className="panel-footer"><span>Output size <strong>{active.resolution}px</strong></span><button className="primary" onClick={() => void runStage("references")} disabled={!canRunStage(active, "references", capabilities) || busy}>{activeStage?.status === "RUNNING" ? "Working…" : "Process images"}</button></div></div>
            <div className="panel hardware"><div className="panel-header"><div><span className="eyebrow">YOUR COMPUTER</span><h3>Ready to build</h3></div><span className="pill good">{hardware?.recommendation ?? "CHECKING"}</span></div>{gpu ? <div className="metric"><div className="metric-icon">▣</div><div><strong>{gpu.name}</strong><span>{(gpu.vram_mb / 1024).toFixed(1)} GB VRAM · {hardware?.ram.total_gb ?? "—"} GB RAM</span></div></div> : <div className="metric"><div className="metric-icon">!</div><div><strong>NVIDIA GPU not detected</strong><span>GPU stages will stay unavailable until a compatible driver is installed</span></div></div>}<div className="metric-row"><span>Blender</span><strong className={hardware?.blender.available ? "text-good" : "text-warning"}>{hardware?.blender.available ? "Ready" : "Install to unlock mesh tools"}</strong></div><div className="metric-row"><span>Local storage</span><strong>{hardware?.disk.free_gb ?? "—"} GB free</strong></div></div></div>
          <div className="panel stages"><div className="panel-header"><div><span className="eyebrow">PROGRESS</span><h3>Build steps</h3></div><span className="muted">One worker at a time</span></div><div className="stage-list">{stageOrder.map(stage => { const record = active.stages[stage]; const canRun = canRunStage(active, stage, capabilities); const reason = blockedReason(active, stage, capabilities); const meta = stageMeta[stage]; const running = record?.status === "RUNNING"; const optional = (stage === "equipment" && active.equipment_assets.length === 0) || (stage === "clothing" && active.clothing_assets.length === 0); return <div className={`stage-row ${running ? "working" : ""}`} key={stage}><span className={`stage-number ${record?.status === "READY" ? "done" : running ? "active" : ""}`}>{record?.status === "READY" ? "✓" : meta.icon}</span><div className="stage-name"><strong>{meta.label}</strong><small>{record?.status === "READY" ? "Complete" : running ? "Working now…" : reason}</small></div><span className={`stage-status ${record?.status === "READY" ? "ready" : record?.status === "FAILED" || record?.status === "FAILED_OOM" ? "failed" : running ? "working" : ""}`}>{optional ? "Optional" : statusLabel(record?.status)}</span><button className={`stage-action ${running ? "cancel" : ""}`} title={running ? "Stop this stage" : canRun ? meta.action : reason} onClick={() => void (running ? cancelStage(stage) : runStage(stage))} disabled={busy || (!canRun && !running)}>{running ? "Stop" : canRun ? meta.action : optional ? "Skip" : "Locked"}</button></div>; })}</div></div>
          {active.stages.rig?.status === "READY" && <div className="panel motion-library"><div className="panel-header"><div><span className="eyebrow">CHOOSE WHAT IT CAN DO</span><h3>Animation library</h3></div><span className={`pill ${active.motion_clips.length ? "good" : "neutral"}`}>{active.motion_clips.length} selected</span></div><p className="panel-note">Pick the movements you want. The next button will normalize them onto this character.</p><div className="motion-grid">{(motionCatalog?.available_clips ?? []).map(clip => <button key={clip.id} className={`motion-card ${active.motion_clips.includes(clip.id) ? "selected" : ""}`} onClick={() => void toggleMotion(clip.id)} disabled={busy} aria-pressed={active.motion_clips.includes(clip.id)}><span className="motion-check">{active.motion_clips.includes(clip.id) ? "✓" : "＋"}</span><strong>{clip.name.replaceAll("_", " ")}</strong><small>{clip.category ?? "motion"}{clip.duration ? ` · ${clip.duration.toFixed(1)}s` : ""}</small></button>)}</div>{active.stages.motions?.status === "READY" && normalizedClips.length > 0 && <><div className="subsection-head"><span className="eyebrow">EXPORT THIS UNIT WITH</span><span className="muted">{active.export_actions.length} selected</span></div><div className="motion-grid export-grid">{normalizedClips.map(clip => { const action = clip.worker?.normalized_action ?? clip.action; return <button key={action} className={`motion-card ${active.export_actions.includes(action) ? "selected" : ""}`} onClick={() => void toggleExportAction(action)} disabled={busy} aria-pressed={active.export_actions.includes(action)}><span className="motion-check">{active.export_actions.includes(action) ? "✓" : "＋"}</span><strong>{clip.action.replaceAll("_", " ")}</strong><small>{clip.category ?? "animation"}</small></button>; })}</div></>}</div>}
          {active.stages.rig?.status === "READY" && <div className="panel motion-library equipment-library"><div className="panel-header"><div><span className="eyebrow">OPTIONAL LOADOUT</span><h3>Equipment</h3></div><span className={`pill ${active.equipment_assets.length ? "good" : "neutral"}`}>{active.equipment_assets.length} equipped</span></div><p className="panel-note">Choose an asset to attach it to the validated skeleton. Leave empty for a body-only unit.</p><div className="motion-grid">{(equipmentCatalog?.assets ?? []).filter(asset => !asset.asset_type.endsWith("_SKINNED")).map(asset => <button key={asset.id} className={`motion-card ${active.equipment_assets.includes(asset.id) ? "selected" : ""}`} onClick={() => void toggleEquipment(asset.id)} disabled={busy} aria-pressed={active.equipment_assets.includes(asset.id)}><span className="motion-check">{active.equipment_assets.includes(asset.id) ? "✓" : "＋"}</span><strong>{asset.name}</strong><small>{asset.asset_type.replaceAll("_", " ")} · {asset.slot.replaceAll("_", " ")}</small></button>)}</div></div>}
          {active.stages.rig?.status === "READY" && <div className="panel motion-library equipment-library"><div className="panel-header"><div><span className="eyebrow">OPTIONAL CLOTHING</span><h3>Clothing</h3></div><span className={`pill ${active.clothing_assets.length ? "good" : "neutral"}`}>{active.clothing_assets.length} selected</span></div><p className="panel-note">Select a garment; Character Factory transfers its weights to this character and reports clipping before export.</p><div className="motion-grid">{(equipmentCatalog?.assets ?? []).filter(asset => asset.asset_type.endsWith("_SKINNED")).map(asset => <button key={asset.id} className={`motion-card ${active.clothing_assets.includes(asset.id) ? "selected" : ""}`} onClick={() => void toggleClothing(asset.id)} disabled={busy} aria-pressed={active.clothing_assets.includes(asset.id)}><span className="motion-check">{active.clothing_assets.includes(asset.id) ? "✓" : "＋"}</span><strong>{asset.name}</strong><small>{asset.asset_type.replaceAll("_", " ")} · {asset.slot.replaceAll("_", " ")}</small></button>)}</div></div>}
          <div className="tester-layout"><Viewport assetUrl={assetUrl} jobId={active.job_id} graphEnabled={active.stages.motions?.status === "READY"} equipmentType={equipmentType} /><div className="panel inspector"><span className="eyebrow">UNIT TESTER</span><h3>{assetUrl ? "Test your character" : "Preview appears here"}</h3><p className="panel-note">{assetUrl ? "Use WASD, Shift, Ctrl and Space. Turn on Skeleton or Wireframe below the viewport." : "A validated GLB will appear here after the shape stage completes."}</p><div className="inspector-row"><span>Images</span><strong className={activeStage?.status === "READY" ? "text-good" : "text-warning"}>{activeStage?.status === "READY" ? "Processed" : "Waiting"}</strong></div><div className="inspector-row"><span>Character asset</span><strong className={assetUrl ? "text-good" : "text-warning"}>{assetStage ? stageMeta[assetStage.name]?.label ?? "Ready" : "Not built yet"}</strong></div><div className="inspector-row"><span>Animation graph</span><strong className={active.stages.motions?.status === "READY" ? "text-good" : "text-warning"}>{active.stages.motions?.status === "READY" ? `Connected${equipmentType ? ` · ${equipmentType}` : ""}` : "Unlocks after motions"}</strong></div>{active.warnings.length > 0 && <div className="quality-warning"><span>QUALITY NOTE</span><p>{active.warnings[0]}</p></div>}{finalGlbUrl && <a className="secondary wide download-link" href={finalGlbUrl} download="character-unit.glb">Download final GLB</a>}<button className="secondary wide" onClick={() => window.open(`/api/jobs/${active.job_id}/events`, "_blank")}>View live activity</button></div></div>
        </>}</section><aside className="results-panel"><div className="results-header"><div><span className="eyebrow">RESULTS</span><h3>Local gallery</h3></div><span className="pill neutral">{resultJobs.length}</span></div><p className="panel-note">Only validated exports from this computer appear here.</p>{resultJobs.length === 0 ? <div className="results-empty"><span>◇</span><p>Your finished character will appear here.</p></div> : <div className="result-list">{resultJobs.map(job => { const front = job.references.front?.original_path; const preview = front ? `/api/jobs/${job.job_id}/files/${front.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/")}` : undefined; return <button key={job.job_id} className={`result-card ${active?.job_id === job.job_id ? "selected" : ""}`} onClick={() => setActive(job)}><div className="result-thumb">{preview ? <img src={preview} alt="Front reference" /> : <span>◇</span>}</div><div className="result-card-copy"><strong>{job.job_id.slice(0, 8)}</strong><small>GLB ready · {job.export_actions.length} animations</small><span>{job.equipment_assets.length ? "With equipment" : "Character only"}</span></div></button>; })}</div>}</aside>
    </main>
  </div>;
}
export default App;
