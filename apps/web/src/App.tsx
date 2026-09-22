import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Capabilities, EquipmentCatalog, Hardware, Job, MotionCatalog, StageRecord, ViewName } from "./api";
import Viewport from "./Viewport";
import RetopologyControls from "./RetopologyControls";
import QualityControls from "./QualityControls";
import AcceptanceSummary from "./AcceptanceSummary";

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

function jobStatusLabel(status?: string): string {
  if (status === "READY") return "Готово";
  if (status === "RUNNING") return "В работе";
  if (status === "FAILED" || status === "FAILED_OOM") return "Нужно внимание";
  if (status === "CANCELLED") return "Остановлено";
  if (status === "INVALIDATED") return "Изменён";
  return "Ожидает";
}

function jobStatusIcon(status?: string): string {
  if (status === "READY") return "✓";
  if (status === "FAILED" || status === "FAILED_OOM") return "!";
  if (status === "CANCELLED") return "×";
  if (status === "RUNNING") return "◇";
  return "·";
}

function jobFileUrl(jobId: string, path: string): string {
  return `/api/jobs/${jobId}/files/${path.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/")}`;
}

function stageOutputPath(record?: StageRecord): string | undefined {
  if (!record) return undefined;
  for (const key of ["glb_path", "mesh_path", "textured_mesh", "output_mesh", "source_mesh"]) {
    const value = record.result[key];
    if (typeof value === "string" && value) return value;
  }
  return undefined;
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
  const graph = job.stages.motions?.result?.graph as { missing_states?: string[] } | undefined;
  if (job.stages.motions?.status === "READY" && (graph?.missing_states?.length ?? 0) > 0) {
    return { title: "Анимации: не хватает состояний", body: `Добавьте: ${graph?.missing_states?.join(", ")}.`, stage: "motions", action: "Повторить анимации", tone: "blocked" };
  }
  if (job.stages.export?.status === "READY") {
    const viewCount = Object.values(job.references).filter(slot => slot.quality?.level !== "ERROR").length;
    const body = viewCount < 2
      ? "GLB готов, но создан по одному ракурсу. Для заметно более точной формы добавьте LEFT, BACK и RIGHT и повторите форму."
      : "Проверенный GLB доступен в галерее результатов.";
    return { title: viewCount < 2 ? "Юнит готов с ограничением" : "Юнит готов", body, tone: "done" };
  }
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

function jobMaturity(job: Job): number {
  const order = ["references", "geometry", "textures", "retopology", "rig", "ik", "motions", "export"];
  return order.reduce((score, stage, index) => score + (job.stages[stage]?.status === "READY" ? index + 1 : 0), 0);
}

function App() {
  const [hardware, setHardware] = useState<Hardware>();
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [motionCatalog, setMotionCatalog] = useState<MotionCatalog>();
  const [equipmentCatalog, setEquipmentCatalog] = useState<EquipmentCatalog>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [cacheItems, setCacheItems] = useState<Array<{ job_id: string; cache_bytes: number; cleanable: boolean; reason: string }>>([]);
  const [active, setActive] = useState<Job>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setJobsLoading(true);
    const [hardwareResult, capabilitiesResult, jobsResult, motionsResult, equipmentResult, cacheResult] = await Promise.allSettled([api.hardware(), api.capabilities(), api.jobs(), api.motions(), api.equipment(), api.cache()]);
    if (hardwareResult.status === "fulfilled") setHardware(hardwareResult.value);
    if (capabilitiesResult.status === "fulfilled") setCapabilities(capabilitiesResult.value);
    if (jobsResult.status === "fulfilled") {
      setJobs(jobsResult.value);
      const mostComplete = [...jobsResult.value].sort((left, right) => jobMaturity(right) - jobMaturity(left))[0];
      setActive(current => current ? jobsResult.value.find(job => job.job_id === current.job_id) ?? current : mostComplete);
    }
    if (motionsResult.status === "fulfilled") setMotionCatalog(motionsResult.value);
    if (equipmentResult.status === "fulfilled") setEquipmentCatalog(equipmentResult.value);
    if (cacheResult.status === "fulfilled") setCacheItems(cacheResult.value.items);
    setJobsLoading(false);
    const criticalFailure = [capabilitiesResult, jobsResult, cacheResult].find(result => result.status === "rejected");
    if (criticalFailure?.status === "rejected") setError(criticalFailure.reason instanceof Error ? criticalFailure.reason.message : String(criticalFailure.reason));
    else setError("");
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => { void Promise.all([api.jobs(), api.hardware()]).then(([list, nextHardware]) => { setJobs(list); setHardware(nextHardware); const next = list.find(job => job.job_id === active.job_id); if (next) setActive(next); }).catch(() => undefined); }, 2000); return () => window.clearInterval(timer); }, [active?.job_id]);

  const create = async () => { setBusy(true); setError(""); try { const job = await api.createJob({ name: "Character Unit", profile: hardware?.recommendation ?? "BALANCED", resolution: 768, requested_provider: "AUTO" }); setActive(job); setJobs(list => [job, ...list]); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const upload = async (view: ViewName, file?: File) => { if (!active || !file) return; setBusy(true); setError(""); try { const job = await api.upload(active.job_id, view, file); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const runStage = async (stage: string) => { if (!active) return; setBusy(true); setError(""); setActive(optimisticRunning(active, stage)); try { await api.runStage(active.job_id, stage); } catch (err) { setError(err instanceof Error ? err.message : String(err)); void refresh(); } finally { setBusy(false); } };
  const buildUnit = async () => { if (!active) return; setBusy(true); setError(""); try { await api.build(active.job_id); setActive({ ...active, status: "RUNNING" }); } catch (err) { setError(err instanceof Error ? err.message : String(err)); void refresh(); } finally { setBusy(false); } };
  const cancelBuild = async () => { if (!active) return; setBusy(true); setError(""); try { await api.cancelBuild(active.job_id); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const cancelStage = async (stage: string) => { if (!active) return; setBusy(true); setError(""); try { await api.cancelStage(active.job_id, stage); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleMotion = async (clipId: string) => { if (!active) return; setBusy(true); setError(""); const clips = active.motion_clips.includes(clipId) ? active.motion_clips.filter(id => id !== clipId) : [...active.motion_clips, clipId]; try { const job = await api.setMotionSelection(active.job_id, clips); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleExportAction = async (action: string) => { if (!active) return; setBusy(true); setError(""); const actions = active.export_actions.includes(action) ? active.export_actions.filter(item => item !== action) : [...active.export_actions, action]; try { const job = await api.setExportSelection(active.job_id, actions); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleEquipment = async (assetId: string) => { if (!active) return; setBusy(true); setError(""); const assets = active.equipment_assets.includes(assetId) ? active.equipment_assets.filter(id => id !== assetId) : [...active.equipment_assets, assetId]; try { const job = await api.setEquipmentSelection(active.job_id, assets); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const toggleClothing = async (assetId: string) => { if (!active) return; setBusy(true); setError(""); const assets = active.clothing_assets.includes(assetId) ? active.clothing_assets.filter(id => id !== assetId) : [...active.clothing_assets, assetId]; try { const job = await api.setClothingSelection(active.job_id, assets); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const updateRetopology = async (mode: Job["retopology_mode"], targetFaces: number) => { if (!active) return; setBusy(true); setError(""); try { const job = await api.setRetopologySettings(active.job_id, mode, targetFaces); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const updateJobSettings = async (settings: Pick<Job, "profile" | "resolution" | "requested_provider" | "inference_steps" | "octree_resolution" | "geometry_num_chunks" | "low_vram_mode" | "texture_resolution">) => { if (!active) return; setBusy(true); setError(""); try { const job = await api.setJobSettings(active.job_id, settings); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const activeStage = active?.stages.references;
  const gpu = hardware?.gpu.gpus[0];
  const geometryVram = active?.stages.geometry?.result.vram as { peak?: { used_bytes?: number; total_bytes?: number } } | undefined;
  const geometryPeakGb = typeof geometryVram?.peak?.used_bytes === "number" ? geometryVram.peak.used_bytes / 1024 ** 3 : undefined;
  const geometryPeakTotalGb = typeof geometryVram?.peak?.total_bytes === "number" ? geometryVram.peak.total_bytes / 1024 ** 3 : undefined;
  const geometryTotalGb = geometryPeakTotalGb ?? (gpu ? gpu.vram_mb / 1024 : 0);
  const readyViews = useMemo(() => Object.values(active?.references ?? {}).filter(slot => slot.quality?.level !== "ERROR").length, [active]);
  const singleViewWarning = active && readyViews === 1 && active.actual_provider?.startsWith("Hunyuan")
    ? "Один ракурс: скрытая сторона и материалы приблизительны; для качества уровня Tripo добавьте LEFT, BACK и RIGHT."
    : undefined;
  const providerWarning = active?.fallback_reason ?? undefined;
  const assetStage = ["export", "ik", "equipment", "clothing", "rig", "textures", "retopology", "geometry"].map(stage => active?.stages[stage]).find(stage => stage?.status === "READY");
  const assetPath = typeof assetStage?.result.glb_path === "string"
    ? assetStage.result.glb_path
    : typeof assetStage?.result.mesh_path === "string"
      ? assetStage.result.mesh_path
      : typeof assetStage?.result.source_mesh === "string" ? assetStage.result.source_mesh : undefined;
  // useGLTF caches by URL. A completed rerun must load the new GLB, while
  // unrelated polling/other stage changes must not reset the viewport.
  const assetUrl = active && assetPath ? `${jobFileUrl(active.job_id, assetPath)}?v=${encodeURIComponent(assetStage?.finished_at ?? "legacy")}` : undefined;
  const finalGlbPath = active?.stages.export?.status === "READY" && typeof active.stages.export.result.glb_path === "string" ? active.stages.export.result.glb_path : undefined;
  const finalGlbUrl = active && finalGlbPath ? jobFileUrl(active.job_id, finalGlbPath) : undefined;
  const normalizedClips = useMemo(() => { const raw = active?.stages.motions?.result.clips; return (Array.isArray(raw) ? raw : []) as Array<{ clip_id: string; action: string; category?: string; worker?: { normalized_action?: string } }>; }, [active]);
  const equipmentType = useMemo(() => {
    const selected = equipmentCatalog?.assets.find(asset => active?.equipment_assets.includes(asset.id));
    const tags = (selected?.tags ?? []).map(tag => tag.toLowerCase());
    return ["rifle", "pistol", "sword", "shield", "staff", "bow"].find(type => tags.includes(type)) ?? null;
  }, [active?.equipment_assets, equipmentCatalog]);
  const resultJobs = useMemo(() => jobs.filter(job => job.stages.export?.status === "READY").slice(0, 20), [jobs]);
  const cleanableCache = useMemo(() => cacheItems.filter(item => item.cleanable && item.cache_bytes > 0), [cacheItems]);
  const next = active ? nextStep(active, capabilities) : undefined;

  const viewConsistency = active?.stages.references?.result?.view_consistency as { level?: string; mean_cosine?: number; min_cosine?: number } | undefined;
  return <div className="app-shell"><nav className="workspace-nav" aria-label="Рабочие разделы"><a className="workspace-nav-item active" href="#references-panel"><span className="workspace-nav-icon">▦</span><span>Активы</span></a><a className="workspace-nav-item" href="#references-panel"><span className="workspace-nav-icon">▣</span><span>Изображение</span></a><a className="workspace-nav-item" href="#viewport-panel"><span className="workspace-nav-icon">◇</span><span>Модель</span></a><a className="workspace-nav-item" href="#animation-panel"><span className="workspace-nav-icon">♧</span><span>Оживить</span></a><a className="workspace-nav-item" href="#export-panel"><span className="workspace-nav-icon">⇩</span><span>Экспорт</span></a></nav>
    <header className="topbar"><div className="brand"><div className="brand-mark">CF</div><div><h1>Character Factory</h1><p>Игровой персонаж локально — от референса до GLB</p></div></div><div className="top-actions"><span className="status-dot" /> ТОЛЬКО ЛОКАЛЬНО {cleanableCache.length > 0 && <button className="secondary" onClick={() => { if (window.confirm(`Удалить промежуточные файлы у ${cleanableCache.length} заброшенных юнитов? Референсы и экспорт защищены.`)) void api.cleanCache(cleanableCache.map(item => item.job_id)).then(() => void refresh()).catch(err => setError(err instanceof Error ? err.message : String(err))); }}>Очистить кэш · {cleanableCache.length}</button>} <button className="secondary" onClick={() => void refresh()}>Обновить</button></div></header>
    <main className="workspace"><aside className="sidebar"><div className="section-head"><span>ЮНИТЫ</span><button className="icon-button" onClick={() => void create()} disabled={busy} aria-label="Создать новый юнит" title="Создать новый юнит">＋</button></div>{jobsLoading && <p className="muted">Загружаем локальные юниты…</p>}{!jobsLoading && jobs.length === 0 && <p className="muted">Создайте первый юнит</p>}{jobs.map(job => <button key={job.job_id} className={`job-row ${active?.job_id === job.job_id ? "selected" : ""}`} onClick={() => setActive(job)}><span className={`job-icon ${job.status === "RUNNING" ? "pulse" : ""} ${job.status === "FAILED" || job.status === "FAILED_OOM" ? "attention" : ""}`}>{jobStatusIcon(job.status)}</span><span><strong>{job.job_id.slice(0, 8)}</strong><small>{jobStatusLabel(job.status)}</small></span></button>)}<div className="sidebar-bottom"><span>ЛОКАЛЬНОЕ РАБОЧЕЕ МЕСТО</span><strong>Данные не покидают компьютер</strong></div></aside>
      <section className="content"><div className="content-title"><div><div className="eyebrow">{active ? `ЮНИТ ${active.job_id.slice(0, 8)}` : "ДОБРО ПОЖАЛОВАТЬ"}</div><h2>{active ? "Соберите персонажа" : "Character Factory"}</h2></div><div className="title-actions">{active && active.status === "RUNNING" ? <button className="secondary" onClick={() => void cancelBuild()} disabled={busy}>Остановить сборку</button> : active && active.references.front ? <button className="primary" onClick={() => void buildUnit()} disabled={busy}>Собрать юнит</button> : null}<button className="primary" onClick={() => void create()} disabled={busy}>＋ Новый юнит</button></div></div>{error && <div className="error-banner"><strong>Нужно внимание</strong><span>{error}</span></div>}
        {!active && jobsLoading ? <div className="welcome loading-state"><h3>Загружаем рабочее пространство</h3><p>Проверяем локальные юниты и состояние генерации.</p><span className="loading-pulse" aria-label="Загрузка" /></div> : !active && error ? <div className="welcome error-state"><h3>Не удалось загрузить локальные юниты</h3><p>{error}</p><button className="primary" onClick={() => void refresh()}>Повторить</button></div> : !active ? <div className="welcome"><h3>Начните с одного изображения персонажа</h3><p>Система проведёт юнит через форму, скелет, движения и экспорт.</p><button className="primary" onClick={() => void create()}>Создать юнит</button></div> : <>
          {next && <div className={`next-card ${next.tone}`}><div className="next-icon">{next.tone === "done" ? "✓" : next.tone === "blocked" ? "!" : "→"}</div><div className="next-copy"><span className="eyebrow">NEXT STEP</span><h3>{next.title}</h3><p>{next.body}</p></div>{next.stage && <button className="primary" onClick={() => void runStage(next.stage!)} disabled={busy}>{next.action}</button>}</div>}
          <div className="dashboard-grid"><div className="panel references"><div className="panel-header"><div><span className="eyebrow">НАЧНИТЕ ЗДЕСЬ</span><h3>Изображения персонажа</h3></div><span className={`pill ${readyViews ? "good" : "neutral"}`}>{readyViews}/4</span></div><p className="panel-note">FRONT запускает сборку. LEFT, BACK и RIGHT заметно улучшают форму, руки и скрытые стороны.</p><div className="reference-grid">{views.map(view => { const slot = active.references[view.id]; return <label key={view.id} className={`drop-slot ${slot ? "has-file" : ""}`}><input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void upload(view.id, event.target.files?.[0])} /><span className="slot-label">{view.label}{view.required && <sup>*</sup>}</span>{slot ? <><span className="slot-check">✓</span><small>{slot.quality?.level ?? "Готово к обработке"}</small></> : <span className="upload-hint">Перетащите или выберите</span>}</label>; })}</div><div className="panel-footer"><span>Размер <strong>{active.resolution}px</strong></span><button className="primary" onClick={() => void runStage("references")} disabled={!canRunStage(active, "references", capabilities) || busy}>{activeStage?.status === "RUNNING" ? "Обрабатываем…" : "Обработать изображения"}</button></div></div>
            <div className="panel hardware"><div className="panel-header"><div><span className="eyebrow">ВАШ КОМПЬЮТЕР</span><h3>Готов к сборке</h3></div><span className="pill good">{hardware?.recommendation ?? "ПРОВЕРЯЕМ"}</span></div>{gpu ? <div className="metric"><div className="metric-icon">▣</div><div><strong>{gpu.name}</strong><span>{(gpu.vram_mb / 1024).toFixed(1)} ГБ VRAM · {hardware?.ram.total_gb ?? "—"} ГБ RAM</span></div></div> : <div className="metric"><div className="metric-icon">!</div><div><strong>Видеокарта NVIDIA не найдена</strong><span>GPU-этапы недоступны, пока не установлен совместимый драйвер</span></div></div>}{gpu && typeof gpu.used_vram_mb === "number" && <div className="metric-row"><span>VRAM сейчас</span><strong>{(gpu.used_vram_mb / 1024).toFixed(2)} / {(gpu.vram_mb / 1024).toFixed(2)} ГБ</strong></div>}{geometryPeakGb !== undefined && <div className="metric-row"><span>Пик geometry-stage</span><strong>{geometryPeakGb.toFixed(2)} / {geometryTotalGb.toFixed(2)} ГБ</strong></div>}<div className="metric-row"><span>Blender</span><strong className={hardware?.blender.available ? "text-good" : "text-warning"}>{hardware?.blender.available ? "Готов" : "Установите Blender для сетки"}</strong></div><div className="metric-row"><span>Свободное место</span><strong>{hardware?.disk.free_gb ?? "—"} ГБ</strong></div></div></div>
          <AcceptanceSummary jobId={active.job_id} updatedAt={active.updated_at} /><div className="panel quality-panel"><QualityControls job={active} busy={busy} onSave={updateJobSettings} /></div><div className="panel stages"><div className="panel-header"><div><span className="eyebrow">ХОД СБОРКИ</span><h3>Шаги создания</h3></div><span className="muted">Одновременно работает один шаг</span></div><div className="stage-list">{stageOrder.map(stage => { const record = active.stages[stage]; const canRun = canRunStage(active, stage, capabilities); const reason = blockedReason(active, stage, capabilities); const meta = stageMeta[stage]; const running = record?.status === "RUNNING"; const optional = (stage === "equipment" && active.equipment_assets.length === 0) || (stage === "clothing" && active.clothing_assets.length === 0); const outputPath = stageOutputPath(record); const logUrl = record?.log_path ? jobFileUrl(active.job_id, `logs/${stage}.log`) : undefined; return <div className={`stage-row ${running ? "working" : ""}`} key={stage}><span className={`stage-number ${record?.status === "READY" ? "done" : running ? "active" : ""}`}>{record?.status === "READY" ? "✓" : meta.icon}</span><div className="stage-name"><strong>{meta.label}</strong><small>{record?.status === "READY" ? "Готово" : running ? "Сейчас выполняется…" : reason}</small>{stage === "retopology" && <RetopologyControls mode={active.retopology_mode} targetFaces={active.retopology_target_faces} busy={busy} onSave={updateRetopology} />}</div><span className={`stage-status ${record?.status === "READY" ? "ready" : record?.status === "FAILED" || record?.status === "FAILED_OOM" ? "failed" : running ? "working" : ""}`}>{optional ? "Можно пропустить" : statusLabel(record?.status)}</span><div className="stage-links">{outputPath && <a href={jobFileUrl(active.job_id, outputPath)} target="_blank" rel="noreferrer" aria-label={`Открыть результат: ${meta.label}`} title="Открыть результат">↗</a>}{logUrl && <a href={logUrl} target="_blank" rel="noreferrer" aria-label={`Открыть журнал: ${meta.label}`} title="Открыть журнал">≡</a>}</div><button className={`stage-action ${running ? "cancel" : ""}`} title={running ? "Остановить этот шаг" : canRun ? meta.action : reason} onClick={() => void (running ? cancelStage(stage) : runStage(stage))} disabled={busy || (!canRun && !running)}>{running ? "Остановить" : canRun ? meta.action : optional ? "Пропустить" : "Заблокировано"}</button></div>; })}</div></div>
          {active.stages.rig?.status === "READY" && <div className="panel motion-library"><div className="panel-header"><div><span className="eyebrow">ВЫБЕРИТЕ ДЕЙСТВИЯ</span><h3>Библиотека анимаций</h3></div><span className={`pill ${active.motion_clips.length ? "good" : "neutral"}`}>{active.motion_clips.length} выбрано</span></div><p className="panel-note">Отметьте движения персонажа. Следующий запуск перенесёт их на этот скелет.</p><div className="motion-grid">{(motionCatalog?.available_clips ?? []).map(clip => <button key={clip.id} className={`motion-card ${active.motion_clips.includes(clip.id) ? "selected" : ""}`} onClick={() => void toggleMotion(clip.id)} disabled={busy} aria-pressed={active.motion_clips.includes(clip.id)}><span className="motion-check">{active.motion_clips.includes(clip.id) ? "✓" : "＋"}</span><strong>{clip.name.replaceAll("_", " ")}</strong><small>{clip.category ?? "движение"}{clip.duration ? ` · ${clip.duration.toFixed(1)}с` : ""}</small></button>)}</div>{active.stages.motions?.status === "READY" && normalizedClips.length > 0 && <><div className="subsection-head"><span className="eyebrow">В ЭКСПОРТ ПОПАДУТ</span><span className="muted">{active.export_actions.length} выбрано</span></div><div className="motion-grid export-grid">{normalizedClips.map(clip => { const action = clip.worker?.normalized_action ?? clip.action; return <button key={action} className={`motion-card ${active.export_actions.includes(action) ? "selected" : ""}`} onClick={() => void toggleExportAction(action)} disabled={busy} aria-pressed={active.export_actions.includes(action)}><span className="motion-check">{active.export_actions.includes(action) ? "✓" : "＋"}</span><strong>{clip.action.replaceAll("_", " ")}</strong><small>{clip.category ?? "анимация"}</small></button>; })}</div></>}</div>}
          {active.stages.rig?.status === "READY" && <div className="panel motion-library equipment-library"><div className="panel-header"><div><span className="eyebrow">OPTIONAL LOADOUT</span><h3>Equipment</h3></div><span className={`pill ${active.equipment_assets.length ? "good" : "neutral"}`}>{active.equipment_assets.length} equipped</span></div><p className="panel-note">Choose an asset to attach it to the validated skeleton. Leave empty for a body-only unit.</p><div className="motion-grid">{(equipmentCatalog?.assets ?? []).filter(asset => !asset.asset_type.endsWith("_SKINNED")).map(asset => <button key={asset.id} className={`motion-card ${active.equipment_assets.includes(asset.id) ? "selected" : ""}`} onClick={() => void toggleEquipment(asset.id)} disabled={busy} aria-pressed={active.equipment_assets.includes(asset.id)}><span className="motion-check">{active.equipment_assets.includes(asset.id) ? "✓" : "＋"}</span><strong>{asset.name}</strong><small>{asset.asset_type.replaceAll("_", " ")} · {asset.slot.replaceAll("_", " ")}</small></button>)}</div></div>}
          {active.stages.rig?.status === "READY" && <div className="panel motion-library equipment-library"><div className="panel-header"><div><span className="eyebrow">OPTIONAL CLOTHING</span><h3>Clothing</h3></div><span className={`pill ${active.clothing_assets.length ? "good" : "neutral"}`}>{active.clothing_assets.length} selected</span></div><p className="panel-note">Select a garment; Character Factory transfers its weights to this character and reports clipping before export.</p><div className="motion-grid">{(equipmentCatalog?.assets ?? []).filter(asset => asset.asset_type.endsWith("_SKINNED")).map(asset => <button key={asset.id} className={`motion-card ${active.clothing_assets.includes(asset.id) ? "selected" : ""}`} onClick={() => void toggleClothing(asset.id)} disabled={busy} aria-pressed={active.clothing_assets.includes(asset.id)}><span className="motion-check">{active.clothing_assets.includes(asset.id) ? "✓" : "＋"}</span><strong>{asset.name}</strong><small>{asset.asset_type.replaceAll("_", " ")} · {asset.slot.replaceAll("_", " ")}</small></button>)}</div></div>}
          <div className="tester-layout"><Viewport assetUrl={assetUrl} jobId={active.job_id} graphEnabled={active.stages.motions?.status === "READY"} equipmentType={equipmentType} /><div className="panel inspector"><span className="eyebrow">ПРОВЕРКА ЮНИТА</span><h3>{assetUrl ? "Персонаж готов к проверке" : "Предпросмотр появится здесь"}</h3><p className="panel-note">{assetUrl ? "WASD, Shift, Ctrl и Space управляют просмотром. Скелет и каркас включаются под окном." : "Проверенный GLB появится после создания формы."}</p><div className="inspector-row"><span>Изображения</span><strong className={activeStage?.status === "READY" ? "text-good" : "text-warning"}>{activeStage?.status === "READY" ? `${readyViews}/4 обработано` : "Ожидают"}</strong></div><div className="inspector-row"><span>Источник формы</span><strong className={assetUrl ? "text-good" : "text-warning"}>{active.actual_provider?.replace("Provider", "") ?? "Автовыбор"}</strong></div><div className="inspector-row"><span>Модель персонажа</span><strong className={assetUrl ? "text-good" : "text-warning"}>{assetStage ? stageMeta[assetStage.name]?.label ?? "Готово" : "Ещё не создана"}</strong></div><div className="inspector-row"><span>Граф анимации</span><strong className={active.stages.motions?.status === "READY" ? "text-good" : "text-warning"}>{active.stages.motions?.status === "READY" ? `Подключён${equipmentType ? ` · ${equipmentType}` : ""}` : "Появится после анимаций"}</strong></div>{viewConsistency && <div className="inspector-row"><span>Согласованность ракурсов</span><strong className={viewConsistency.level === "GOOD" ? "text-good" : "text-warning"}>{viewConsistency.level === "GOOD" ? `Хорошая · ${(viewConsistency.mean_cosine ?? 0).toFixed(2)}` : "Нужно проверить"}</strong></div>}{(providerWarning || singleViewWarning || active.warnings.length > 0) && <div className="quality-warning"><span>ЧТО ВЛИЯЕТ НА КАЧЕСТВО</span><p>{providerWarning ?? singleViewWarning ?? active.warnings[0]}</p></div>}{finalGlbUrl && <a className="secondary wide download-link" href={finalGlbUrl} download="character-unit.glb">Скачать финальный GLB</a>}<button className="secondary wide" onClick={() => window.open(`/api/jobs/${active.job_id}/events`, "_blank")}>Открыть журнал</button></div></div>
        </>}</section><aside className="results-panel"><div className="results-header"><div><span className="eyebrow">РЕЗУЛЬТАТЫ</span><h3>Локальная галерея</h3></div><span className="pill neutral">{resultJobs.length}</span></div><p className="panel-note">Здесь появляются только проверенные экспорты с этого компьютера.</p>{resultJobs.length === 0 ? <div className="results-empty"><span>◇</span><p>Готовый персонаж появится здесь.</p></div> : <div className="result-list">{resultJobs.map(job => { const front = job.references.front?.original_path; const preview = front ? `/api/jobs/${job.job_id}/files/${front.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/")}` : undefined; return <button key={job.job_id} className={`result-card ${active?.job_id === job.job_id ? "selected" : ""}`} onClick={() => setActive(job)}><div className="result-thumb">{preview ? <img src={preview} alt="Референс FRONT" /> : <span>◇</span>}</div><div className="result-card-copy"><strong>{job.job_id.slice(0, 8)}</strong><small>GLB готов · {job.export_actions.length} анимаций</small><span>{job.equipment_assets.length ? "С экипировкой" : "Только персонаж"}</span></div></button>; })}</div>}</aside>
    </main>
  </div>;
}
export default App;
