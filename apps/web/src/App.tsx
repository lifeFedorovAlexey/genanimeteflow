import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Capabilities, Hardware, Job, StageRecord, ViewName } from "./api";
import Viewport from "./Viewport";

const views: Array<{ id: ViewName; label: string; required: boolean }> = [
  { id: "front", label: "FRONT", required: true }, { id: "left", label: "LEFT", required: false }, { id: "back", label: "BACK", required: false }, { id: "right", label: "RIGHT", required: false },
];

const stageOrder = ["references", "geometry", "textures", "retopology", "rig", "equipment", "motions", "export"];
const stageMeta: Record<string, { label: string; action: string; icon: string }> = {
  references: { label: "Reference images", action: "Process images", icon: "01" },
  geometry: { label: "3D shape", action: "Generate shape", icon: "02" },
  textures: { label: "Materials", action: "Extract materials", icon: "03" },
  retopology: { label: "Game topology", action: "Optimize mesh", icon: "04" },
  rig: { label: "Skeleton", action: "Build skeleton", icon: "05" },
  equipment: { label: "Equipment", action: "Attach equipment", icon: "06" },
  motions: { label: "Animations", action: "Normalize motions", icon: "07" },
  export: { label: "Export unit", action: "Export unit", icon: "08" },
};

function statusLabel(status?: string): string {
  if (status === "READY") return "Ready";
  if (status === "RUNNING") return "In progress";
  if (status === "FAILED" || status === "FAILED_OOM") return "Needs attention";
  if (status === "CANCELLED") return "Stopped";
  return "Waiting";
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
  if (stage === "motions") return job.stages.rig?.status === "READY" && job.motion_clips.length > 0;
  if (stage === "export") return job.stages.motions?.status === "READY" && job.export_actions.length > 0;
  return false;
}

function blockedReason(job: Job, stage: string, capabilities?: Capabilities): string {
  const record = job.stages[stage];
  if (record?.error_message) return record.error_message;
  if (!capabilities?.stages[stage]?.available) return capabilities?.stages[stage]?.reason ?? "This tool is not available on this computer";
  if (stage === "references" && !job.references.front) return "Add a FRONT image first";
  if (stage === "geometry" && job.stages.references?.status !== "READY") return "Process the reference images first";
  if (stage === "textures" && job.stages.geometry?.status !== "READY") return "Generate the 3D shape first";
  if (stage === "retopology" && job.stages.textures?.status !== "READY") return "Extract materials first";
  if (stage === "rig" && job.stages.retopology?.status !== "READY") return "Optimize the mesh first";
  if (stage === "equipment" && job.equipment_assets.length === 0) return "Choose equipment in the asset library first";
  if (stage === "equipment" && job.stages.rig?.status !== "READY") return "Build the skeleton first";
  if (stage === "motions" && job.motion_clips.length === 0) return "Choose motion clips in the motion library first";
  if (stage === "motions" && job.stages.rig?.status !== "READY") return "Build the skeleton first";
  if (stage === "export" && job.export_actions.length === 0) return "Choose at least one animation to export";
  if (stage === "export" && job.stages.motions?.status !== "READY") return "Normalize motions first";
  return "Waiting for the previous step";
}

function nextStep(job: Job, capabilities?: Capabilities): { title: string; body: string; stage?: string; action?: string; tone: "action" | "blocked" | "done" } {
  if (!job.references.front) return { title: "Add the character FRONT image", body: "Drop a full-body front view into the first slot to begin.", stage: "references", action: "Add FRONT image", tone: "action" };
  const failed = stageOrder.map(stage => ({ stage, record: job.stages[stage] })).find(item => item.record?.status === "FAILED" || item.record?.status === "FAILED_OOM");
  if (failed) return { title: `${stageMeta[failed.stage].label} needs attention`, body: failed.record.error_message ?? "Open the stage details and run it again.", stage: failed.stage, action: "Try again", tone: "blocked" };
  const running = stageOrder.find(stage => job.stages[stage]?.status === "RUNNING");
  if (running) return { title: `${stageMeta[running].label} is working`, body: "The result will appear here automatically when the worker finishes.", tone: "action" };
  const pending = stageOrder.find(stage => job.stages[stage]?.status !== "READY");
  if (pending) {
    const canRun = canRunStage(job, pending, capabilities);
    return { title: canRun ? stageMeta[pending].action : `Prepare ${stageMeta[pending].label.toLowerCase()}`, body: blockedReason(job, pending, capabilities), stage: canRun ? pending : undefined, action: canRun ? stageMeta[pending].action : undefined, tone: canRun ? "action" : "blocked" };
  }
  return { title: "Character unit is ready", body: "All available stages completed successfully.", tone: "done" };
}

function App() {
  const [hardware, setHardware] = useState<Hardware>();
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [active, setActive] = useState<Job>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => { try { const [hw, caps, list] = await Promise.all([api.hardware(), api.capabilities(), api.jobs()]); setHardware(hw); setCapabilities(caps); setJobs(list); setActive(current => current ? list.find(job => job.job_id === current.job_id) ?? current : list[0]); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { if (!active) return; const timer = window.setInterval(() => { void api.jobs().then(list => { setJobs(list); const next = list.find(job => job.job_id === active.job_id); if (next) setActive(next); }).catch(() => undefined); }, 1000); return () => window.clearInterval(timer); }, [active?.job_id]);

  const create = async () => { setBusy(true); setError(""); try { const job = await api.createJob({ name: "Character Unit", profile: hardware?.recommendation ?? "BALANCED", resolution: 512, requested_provider: "AUTO" }); setActive(job); setJobs(list => [job, ...list]); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const upload = async (view: ViewName, file?: File) => { if (!active || !file) return; setBusy(true); setError(""); try { const job = await api.upload(active.job_id, view, file); setActive(job); setJobs(list => list.map(item => item.job_id === job.job_id ? job : item)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setBusy(false); } };
  const runStage = async (stage: string) => { if (!active) return; setBusy(true); setError(""); setActive(optimisticRunning(active, stage)); try { await api.runStage(active.job_id, stage); } catch (err) { setError(err instanceof Error ? err.message : String(err)); void refresh(); } finally { setBusy(false); } };
  const activeStage = active?.stages.references;
  const gpu = hardware?.gpu.gpus[0];
  const readyViews = useMemo(() => Object.values(active?.references ?? {}).filter(slot => slot.quality?.level !== "ERROR").length, [active]);
  const assetStage = ["equipment", "rig", "textures", "retopology", "geometry"].map(stage => active?.stages[stage]).find(stage => stage?.status === "READY");
  const assetPath = typeof assetStage?.result.mesh_path === "string"
    ? assetStage.result.mesh_path
    : typeof assetStage?.result.source_mesh === "string" ? assetStage.result.source_mesh : undefined;
  // useGLTF caches by URL. A completed rerun must load the new GLB, while
  // unrelated polling/other stage changes must not reset the viewport.
  const assetUrl = active && assetPath ? `/api/jobs/${active.job_id}/files/${assetPath.replace(/\\/g, "/").split("/").map(encodeURIComponent).join("/")}?v=${encodeURIComponent(assetStage?.finished_at ?? "legacy")}` : undefined;
  const next = active ? nextStep(active, capabilities) : undefined;

  return <div className="app-shell">
    <header className="topbar"><div className="brand"><div className="brand-mark">CF</div><div><h1>Character Factory</h1><p>Build a playable character, one clear step at a time</p></div></div><div className="top-actions"><span className="status-dot" /> LOCAL ONLY <button className="secondary" onClick={() => void refresh()}>Refresh</button></div></header>
    <main className="workspace"><aside className="sidebar"><div className="section-head"><span>UNITS</span><button className="icon-button" onClick={() => void create()} disabled={busy}>＋</button></div>{jobs.length === 0 && <p className="muted">Create your first unit</p>}{jobs.map(job => <button key={job.job_id} className={`job-row ${active?.job_id === job.job_id ? "selected" : ""}`} onClick={() => setActive(job)}><span className={`job-icon ${job.status === "RUNNING" ? "pulse" : ""}`}>{job.status === "READY" ? "✓" : "◇"}</span><span><strong>{job.job_id.slice(0, 8)}</strong><small>{job.status === "RUNNING" ? "Working" : job.status === "READY" ? "Ready" : "In progress"}</small></span></button>)}<div className="sidebar-bottom"><span>LOCAL WORKSPACE</span><strong>Nothing leaves this computer</strong></div></aside>
      <section className="content"><div className="content-title"><div><div className="eyebrow">{active ? `UNIT ${active.job_id.slice(0, 8)}` : "WELCOME"}</div><h2>{active ? "Build your character" : "Character Factory"}</h2></div><button className="primary" onClick={() => void create()} disabled={busy}>＋ New unit</button></div>{error && <div className="error-banner"><strong>Something needs attention</strong><span>{error}</span></div>}
        {!active ? <div className="welcome"><h3>Start with one character image</h3><p>We will guide the unit through shape, skeleton, motion and export.</p><button className="primary" onClick={() => void create()}>Create unit</button></div> : <>
          {next && <div className={`next-card ${next.tone}`}><div className="next-icon">{next.tone === "done" ? "✓" : next.tone === "blocked" ? "!" : "→"}</div><div className="next-copy"><span className="eyebrow">NEXT STEP</span><h3>{next.title}</h3><p>{next.body}</p></div>{next.stage && <button className="primary" onClick={() => void runStage(next.stage!)} disabled={busy}>{next.action}</button>}</div>}
          <div className="dashboard-grid"><div className="panel references"><div className="panel-header"><div><span className="eyebrow">START HERE</span><h3>Character images</h3></div><span className={`pill ${readyViews ? "good" : "neutral"}`}>{readyViews}/4</span></div><p className="panel-note">FRONT starts the pipeline. Add the other views when you have them.</p><div className="reference-grid">{views.map(view => { const slot = active.references[view.id]; return <label key={view.id} className={`drop-slot ${slot ? "has-file" : ""}`}><input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => void upload(view.id, event.target.files?.[0])} /><span className="slot-label">{view.label}{view.required && <sup>*</sup>}</span>{slot ? <><span className="slot-check">✓</span><small>{slot.quality?.level ?? "Ready to process"}</small></> : <span className="upload-hint">Drop or browse</span>}</label>; })}</div><div className="panel-footer"><span>Output size <strong>{active.resolution}px</strong></span><button className="primary" onClick={() => void runStage("references")} disabled={!canRunStage(active, "references", capabilities) || busy}>{activeStage?.status === "RUNNING" ? "Working…" : "Process images"}</button></div></div>
            <div className="panel hardware"><div className="panel-header"><div><span className="eyebrow">YOUR COMPUTER</span><h3>Ready to build</h3></div><span className="pill good">{hardware?.recommendation ?? "CHECKING"}</span></div>{gpu ? <div className="metric"><div className="metric-icon">▣</div><div><strong>{gpu.name}</strong><span>{(gpu.vram_mb / 1024).toFixed(1)} GB VRAM · {hardware?.ram.total_gb ?? "—"} GB RAM</span></div></div> : <div className="metric"><div className="metric-icon">!</div><div><strong>NVIDIA GPU not detected</strong><span>GPU stages will stay unavailable until a compatible driver is installed</span></div></div>}<div className="metric-row"><span>Blender</span><strong className={hardware?.blender.available ? "text-good" : "text-warning"}>{hardware?.blender.available ? "Ready" : "Install to unlock mesh tools"}</strong></div><div className="metric-row"><span>Local storage</span><strong>{hardware?.disk.free_gb ?? "—"} GB free</strong></div></div></div>
          <div className="panel stages"><div className="panel-header"><div><span className="eyebrow">PROGRESS</span><h3>Build steps</h3></div><span className="muted">One worker at a time</span></div><div className="stage-list">{stageOrder.map(stage => { const record = active.stages[stage]; const capability = capabilities?.stages[stage]; const canRun = canRunStage(active, stage, capabilities); const reason = blockedReason(active, stage, capabilities); const meta = stageMeta[stage]; return <div className={`stage-row ${record?.status === "RUNNING" ? "working" : ""}`} key={stage}><span className={`stage-number ${record?.status === "READY" ? "done" : record?.status === "RUNNING" ? "active" : ""}`}>{record?.status === "READY" ? "✓" : meta.icon}</span><div className="stage-name"><strong>{meta.label}</strong><small>{record?.status === "READY" ? "Complete" : record?.status === "RUNNING" ? "Working now…" : reason}</small></div><span className={`stage-status ${record?.status === "READY" ? "ready" : record?.status === "FAILED" || record?.status === "FAILED_OOM" ? "failed" : record?.status === "RUNNING" ? "working" : ""}`}>{statusLabel(record?.status)}</span><button className="stage-action" title={canRun ? meta.action : reason} onClick={() => void runStage(stage)} disabled={busy || !canRun || record?.status === "RUNNING"}>{record?.status === "RUNNING" ? "Working…" : canRun ? meta.action : "Locked"}</button></div>; })}</div></div>
          <div className="tester-layout"><Viewport assetUrl={assetUrl} jobId={active.job_id} graphEnabled={active.stages.motions?.status === "READY"} /><div className="panel inspector"><span className="eyebrow">UNIT TESTER</span><h3>{assetUrl ? "Test your character" : "Preview appears here"}</h3><p className="panel-note">{assetUrl ? "Use WASD, Shift, Ctrl and Space. Turn on Skeleton or Wireframe below the viewport." : "A validated GLB will appear here after the shape stage completes."}</p><div className="inspector-row"><span>Images</span><strong className={activeStage?.status === "READY" ? "text-good" : "text-warning"}>{activeStage?.status === "READY" ? "Processed" : "Waiting"}</strong></div><div className="inspector-row"><span>Character asset</span><strong className={assetUrl ? "text-good" : "text-warning"}>{assetStage ? stageMeta[assetStage.name]?.label ?? "Ready" : "Not built yet"}</strong></div><div className="inspector-row"><span>Animation graph</span><strong className={active.stages.motions?.status === "READY" ? "text-good" : "text-warning"}>{active.stages.motions?.status === "READY" ? "Connected" : "Unlocks after motions"}</strong></div>{active.warnings.length > 0 && <div className="quality-warning"><span>QUALITY NOTE</span><p>{active.warnings[0]}</p></div>}<button className="secondary wide" onClick={() => window.open(`/api/jobs/${active.job_id}/events`, "_blank")}>View live activity</button></div></div>
        </>}</section></main>
  </div>;
}
export default App;
