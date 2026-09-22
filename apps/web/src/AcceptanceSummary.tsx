import { useEffect, useState } from "react";
import { api, AcceptanceReport } from "./api";

export default function AcceptanceSummary({ jobId, updatedAt }: { jobId: string; updatedAt: string }) {
  const [report, setReport] = useState<AcceptanceReport>();
  useEffect(() => {
    let active = true;
    void api.acceptance(jobId, true).then(next => { if (active) setReport(next); }).catch(() => { if (active) setReport(undefined); });
    return () => { active = false; };
  }, [jobId, updatedAt]);
  if (!report) return <div className="panel acceptance-panel"><span className="eyebrow">ПРОВЕРКА ПО ТЗ</span><h3>Собираю acceptance-отчёт…</h3></div>;
  const passed = report.checks.filter(check => check.passed).length;
  const failed = report.checks.filter(check => !check.passed);
  return <div className={`panel acceptance-panel ${report.valid ? "accepted" : "attention"}`}>
    <div className="panel-header"><div><span className="eyebrow">ПРОВЕРКА ПО ТЗ</span><h3>{report.valid ? "Полный acceptance пройден" : "Полный acceptance ещё не пройден"}</h3></div><span className={`pill ${report.valid ? "good" : "neutral"}`}>{passed}/{report.checks.length}</span></div>
    <p className="panel-note">Это строгий gate: четыре согласованных ракурса, multiview-геометрия, DINOv3, экипировка, одежда, IK и round-trip export.</p>
    <div className="acceptance-metrics"><span>{report.metrics.vertices.toLocaleString()} вершин</span><span>{report.metrics.textures} текстур</span><span>{report.metrics.bones} костей</span><span>{report.metrics.animations} анимаций</span></div>
    {failed.length > 0 && <details className="acceptance-failures" open><summary>Что не прошло ({failed.length})</summary><div>{failed.map(check => <div className="acceptance-failure" key={check.id}><strong>{check.label}</strong><small>{check.detail}</small></div>)}</div></details>}
  </div>;
}
