export type StageStatus = "PENDING" | "RUNNING" | "READY" | "FAILED" | "FAILED_OOM" | "INVALIDATED" | "CANCELLED";
export type ViewName = "front" | "left" | "back" | "right";
export interface ReferenceSlot { view: ViewName; required: boolean; original_path?: string; processed_path?: string; quality?: { level: "GOOD" | "WARNING" | "ERROR"; warnings: string[]; errors: string[]; foreground_ratio: number; [key: string]: unknown }; }
export interface StageRecord { name: string; status: StageStatus; error_category?: string; error_message?: string; result: Record<string, unknown>; }
export interface Job { job_id: string; status: string; profile: string; resolution: number; references: Record<string, ReferenceSlot>; stages: Record<string, StageRecord>; motion_clips: string[]; export_actions: string[]; updated_at: string; }
export interface Hardware { os: Record<string, unknown>; cpu: Record<string, unknown>; ram: { total_gb: number }; gpu: { available: boolean; gpus: Array<{ name: string; vram_mb: number; driver: string; compute_capability: string }>; }; cuda: Record<string, unknown>; blender: { available: boolean; path?: string }; recommendation: string; disk: { free_gb: number }; }
export interface Capabilities { providers: Record<string, { available: boolean; reason?: string }>; stages: Record<string, { available: boolean; description?: string; reason?: string }>; }
async function request<T>(url: string, init?: RequestInit): Promise<T> { const response = await fetch(url, init); if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `${response.status} ${response.statusText}`); return response.json() as Promise<T>; }
export const api = {
  hardware: () => request<Hardware>("/api/hardware"), capabilities: () => request<Capabilities>("/api/capabilities"), jobs: () => request<Job[]>("/api/jobs"),
  createJob: (body: { name: string; profile: string; resolution: number; requested_provider: string }) => request<Job>("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  upload: (jobId: string, view: ViewName, file: File) => { const form = new FormData(); form.append("file", file); return request<Job>(`/api/jobs/${jobId}/references/${view}`, { method: "POST", body: form }); },
  runStage: (jobId: string, stage: string) => request<{ status: string }>(`/api/jobs/${jobId}/stages/${stage}/run`, { method: "POST" }),
  setExportSelection: (jobId: string, actions: string[]) => request<Job>(`/api/jobs/${jobId}/export-selection`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ actions }) }),
  setMotionSelection: (jobId: string, clips: string[]) => request<Job>(`/api/jobs/${jobId}/motion-selection`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clips }) }),
};
