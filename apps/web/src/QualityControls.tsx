import { useEffect, useState } from "react";
import { Job } from "./api";

type Props = {
  job: Job;
  busy: boolean;
  onSave: (settings: Pick<Job, "profile" | "resolution" | "requested_provider" | "inference_steps" | "octree_resolution" | "geometry_num_chunks" | "low_vram_mode" | "texture_resolution">) => Promise<void>;
};

export default function QualityControls({ job, busy, onSave }: Props) {
  const [profile, setProfile] = useState(job.profile);
  const [resolution, setResolution] = useState(String(job.resolution));
  const [provider, setProvider] = useState(job.requested_provider ?? "AUTO");
  const [steps, setSteps] = useState(String(job.inference_steps));
  const [octree, setOctree] = useState(String(job.octree_resolution));
  const [chunks, setChunks] = useState(String(job.geometry_num_chunks));
  const [lowVram, setLowVram] = useState(job.low_vram_mode);
  const [textureResolution, setTextureResolution] = useState(String(job.texture_resolution));
  useEffect(() => {
    setProfile(job.profile); setResolution(String(job.resolution)); setProvider(job.requested_provider ?? "AUTO");
    setSteps(String(job.inference_steps)); setOctree(String(job.octree_resolution)); setChunks(String(job.geometry_num_chunks));
    setLowVram(job.low_vram_mode); setTextureResolution(String(job.texture_resolution));
  }, [job]);
  const payload = {
    profile,
    resolution: Math.max(384, Math.min(1536, Number(resolution) || job.resolution)),
    requested_provider: provider,
    inference_steps: Math.max(20, Math.min(100, Number(steps) || job.inference_steps)),
    octree_resolution: Math.max(256, Math.min(512, Number(octree) || job.octree_resolution)),
    geometry_num_chunks: Math.max(5000, Math.min(50000, Number(chunks) || job.geometry_num_chunks)),
    low_vram_mode: lowVram,
    texture_resolution: Number(textureResolution) as 512 | 1024 | 2048,
  };
  const dirty = JSON.stringify(payload) !== JSON.stringify({ profile: job.profile, resolution: job.resolution, requested_provider: job.requested_provider ?? "AUTO", inference_steps: job.inference_steps, octree_resolution: job.octree_resolution, geometry_num_chunks: job.geometry_num_chunks, low_vram_mode: job.low_vram_mode, texture_resolution: job.texture_resolution });
  return <details className="quality-settings">
    <summary>Качество и GPU · {job.profile}</summary>
    <div className="quality-fields">
      <label>Профиль<select value={profile} onChange={event => setProfile(event.target.value as Job["profile"])}><option value="SAFE">SAFE · меньше VRAM</option><option value="BALANCED">BALANCED · рекомендуется</option><option value="MAX">MAX · больше время/VRAM</option><option value="CUSTOM">CUSTOM · вручную</option></select></label>
      <label>Размер входа<input type="number" min={384} max={1536} step={64} value={resolution} onChange={event => setResolution(event.target.value)} /></label>
      <label>Provider<select value={provider} onChange={event => setProvider(event.target.value as NonNullable<Job["requested_provider"]>)}><option value="AUTO">AUTO</option><option value="Spar3DProvider">SPAR3D · FRONT</option><option value="HunyuanMultiviewProvider">Hunyuan · multiview</option><option value="HunyuanSingleViewProvider">Hunyuan · single view</option></select></label>
      {profile === "CUSTOM" && <>
        <label>Шаги inference<input type="number" min={20} max={100} step={5} value={steps} onChange={event => setSteps(event.target.value)} /></label>
        <label>Octree<input type="number" min={256} max={512} step={32} value={octree} onChange={event => setOctree(event.target.value)} /></label>
        <label>Chunks<input type="number" min={5000} max={50000} step={1000} value={chunks} onChange={event => setChunks(event.target.value)} /></label>
        <label>Texture<select value={textureResolution} onChange={event => setTextureResolution(event.target.value)}><option value="512">512 px</option><option value="1024">1024 px</option><option value="2048">2048 px · максимум</option></select></label>
        <label className="quality-check"><input type="checkbox" checked={lowVram} onChange={event => setLowVram(event.target.checked)} /> Low VRAM mode</label>
      </>}
      <button className="secondary" type="button" disabled={!dirty || busy} onClick={() => void onSave(payload)}>Применить</button>
    </div>
    <p className="quality-hint">Профиль меняет реальные параметры worker. Размер влияет на сохранённый и переданный референс, но конкретная модель может внутренне уменьшить его; это не обещание качества. После смены provider/качества нужные этапы будут помечены «изменён».</p>
  </details>;
}
