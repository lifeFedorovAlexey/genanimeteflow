import { useEffect, useState } from "react";
import { Job } from "./api";

type Props = {
  mode: Job["retopology_mode"];
  targetFaces: number;
  busy: boolean;
  onSave: (mode: Job["retopology_mode"], targetFaces: number) => Promise<void>;
};

export default function RetopologyControls({ mode, targetFaces, busy, onSave }: Props) {
  const [nextMode, setNextMode] = useState(mode);
  const [nextTarget, setNextTarget] = useState(String(targetFaces));
  useEffect(() => { setNextMode(mode); setNextTarget(String(targetFaces)); }, [mode, targetFaces]);
  const parsedTarget = Math.max(5000, Math.min(80000, Number(nextTarget) || targetFaces));
  const dirty = nextMode !== mode || parsedTarget !== targetFaces;
  return <details className="retopo-settings">
    <summary>Сетка · {mode === "KEEP_SOURCE" ? "исходная" : mode === "QUAD" ? "четырёхугольники" : "треугольники"}</summary>
    <div className="retopo-fields">
      <label>Тип<select value={nextMode} onChange={event => setNextMode(event.target.value as Job["retopology_mode"])}><option value="TRIANGLE">Треугольники</option><option value="QUAD">QUAD</option><option value="KEEP_SOURCE">Оставить исходную</option></select></label>
      <label>Полигоны<input type="number" min={5000} max={80000} step={1000} value={nextTarget} onChange={event => setNextTarget(event.target.value)} /></label>
      <button className="secondary" type="button" disabled={!dirty || busy} onClick={() => void onSave(nextMode, parsedTarget)}>Применить</button>
    </div>
  </details>;
}
