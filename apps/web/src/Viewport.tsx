import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Grid, OrbitControls, useAnimations, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { api } from "./api";

type TesterStatus = { state: string; clip: string; speed: number; time: number; rootMotion: boolean; direction_degrees: number; grounded: boolean; crouched: boolean; sprinting: boolean };

function chooseState(keys: Set<string>): { state: string; speed: number } {
  if (keys.has(" ")) return { state: "jump", speed: 1 };
  if (keys.has("control")) return { state: "crouch", speed: 0.7 };
  if (keys.has("shift")) return { state: "sprint", speed: 2.2 };
  if (keys.has("w") || keys.has("a") || keys.has("s") || keys.has("d")) return { state: "walk", speed: 1.2 };
  return { state: "idle", speed: 1 };
}

function findAction(names: string[], state: string, requested: string): string {
  if (requested && names.includes(requested)) return requested;
  const match = names.find(name => name.toLowerCase().includes(state));
  return match ?? names[0] ?? "";
}

function AnimatedAsset({ url, selectedClip, graphClip, wireframe, skeleton, onActions, onStatus }: { url: string; selectedClip: string; graphClip: string; wireframe: boolean; skeleton: boolean; onActions: (names: string[]) => void; onStatus: (status: TesterStatus) => void }) {
  const root = useRef<THREE.Group>(null);
  const keys = useRef(new Set<string>());
  const activeClip = useRef("");
  const lastStatus = useRef("");
  const asset = useGLTF(url);
  const { actions, mixer } = useAnimations(asset.animations, root);
  const actionNames = useMemo(() => asset.animations.map(animation => animation.name).filter(Boolean), [asset.animations]);
  const skeletonHelper = useMemo(() => new THREE.SkeletonHelper(asset.scene), [asset.scene]);

  useEffect(() => { onActions(actionNames); }, [actionNames, onActions]);
  useEffect(() => {
    const down = (event: KeyboardEvent) => { const key = event.key.toLowerCase(); if ([" ", "shift", "control", "w", "a", "s", "d"].includes(key)) event.preventDefault(); keys.current.add(key); };
    const up = (event: KeyboardEvent) => keys.current.delete(event.key.toLowerCase());
    window.addEventListener("keydown", down); window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, []);
  useEffect(() => {
    asset.scene.traverse(object => {
      if (!(object as THREE.Mesh).isMesh) return;
      const material = (object as THREE.Mesh).material;
      for (const item of Array.isArray(material) ? material : [material]) if (item && "wireframe" in item) item.wireframe = wireframe;
    });
  }, [asset.scene, wireframe]);
  useFrame((_, delta) => {
    const selected = chooseState(keys.current);
    const clip = findAction(actionNames, selected.state, selectedClip || graphClip);
    if (clip && clip !== activeClip.current) {
      const next = actions[clip];
      const previous = activeClip.current ? actions[activeClip.current] : undefined;
      previous?.fadeOut(0.16);
      next?.reset().fadeIn(0.16).play();
      activeClip.current = clip;
    }
    mixer.update(delta * selected.speed);
    const direction = new THREE.Vector3((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), 0, (keys.current.has("s") ? 1 : 0) - (keys.current.has("w") ? 1 : 0));
    if (direction.lengthSq() > 0 && root.current) root.current.position.addScaledVector(direction.normalize(), delta * selected.speed);
    const action = clip ? actions[clip] : undefined;
    const statusKey = `${selected.state}|${clip}|${selected.speed}`;
    if (statusKey !== lastStatus.current) { lastStatus.current = statusKey; const moving = keys.current.has("w") || keys.current.has("a") || keys.current.has("s") || keys.current.has("d"); const angle = Math.atan2((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), (keys.current.has("w") ? 1 : 0) - (keys.current.has("s") ? 1 : 0)) * 180 / Math.PI; onStatus({ state: selected.state, clip, speed: selected.speed, time: action?.time ?? 0, rootMotion: false, direction_degrees: moving ? angle : 0, grounded: !keys.current.has(" "), crouched: keys.current.has("control"), sprinting: keys.current.has("shift") }); }
  });
  return <group ref={root}><primitive object={asset.scene} />{skeleton && <primitive object={skeletonHelper} />}</group>;
}

export default function Viewport({ assetUrl, jobId, graphEnabled }: { assetUrl?: string; jobId?: string; graphEnabled?: boolean }) {
  const [actions, setActions] = useState<string[]>([]);
  const [selectedClip, setSelectedClip] = useState("");
  const [wireframe, setWireframe] = useState(false);
  const [skeleton, setSkeleton] = useState(false);
  const [status, setStatus] = useState<TesterStatus>({ state: "idle", clip: "", speed: 1, time: 0, rootMotion: false, direction_degrees: 0, grounded: true, crouched: false, sprinting: false });
  const [graphClip, setGraphClip] = useState("");
  const handleActions = useCallback((names: string[]) => { setActions(names); setSelectedClip(current => current && names.includes(current) ? current : ""); }, []);
  const handleStatus = useCallback((next: TesterStatus) => { setStatus(next); if (jobId && graphEnabled) void api.evaluateAnimationGraph(jobId, { speed: next.speed, direction_degrees: next.direction_degrees, grounded: next.grounded, crouched: next.crouched, sprinting: next.sprinting, equipment_type: null, action: null, action_time: next.time, combo_index: 0 }).then(result => setGraphClip(result.action_name ?? "")).catch(() => setGraphClip("")); }, [graphEnabled, jobId]);
  return <div className="viewport-shell"><div className="viewport"><Canvas camera={{ position: [3, 2.2, 4], fov: 42 }}><color attach="background" args={["#0c0e12"]} /><ambientLight intensity={1.2} /><directionalLight position={[3, 5, 2]} intensity={2} /><Grid args={[10, 10]} cellColor="#29303a" sectionColor="#4a5666" fadeDistance={12} />{assetUrl && <AnimatedAsset url={assetUrl} selectedClip={selectedClip} graphClip={graphClip} wireframe={wireframe} skeleton={skeleton} onActions={handleActions} onStatus={handleStatus} />}<OrbitControls makeDefault /></Canvas><div className={`viewport-empty ${assetUrl ? "has-asset" : ""}`}><span>{assetUrl ? "Validated asset" : "Unit Tester"}</span><small>{assetUrl ? "WASD move · Shift sprint · Ctrl crouch · Space jump" : "Validated GLB assets will appear here"}</small></div></div>{assetUrl && <div className="tester-toolbar"><label>Clip<select value={selectedClip} onChange={event => setSelectedClip(event.target.value)} disabled={!actions.length}><option value="">Graph / auto state</option>{actions.map(name => <option key={name} value={name}>{name}</option>)}</select></label><label className="debug-toggle"><input type="checkbox" checked={wireframe} onChange={event => setWireframe(event.target.checked)} /> Wireframe</label><label className="debug-toggle"><input type="checkbox" checked={skeleton} onChange={event => setSkeleton(event.target.checked)} /> Skeleton</label><div className="tester-stats"><span>{status.state}</span><span>{status.clip || "no clip"}</span><span>{status.speed.toFixed(1)}×</span><span>{status.rootMotion ? "root motion" : graphEnabled ? "graph" : "in-place"}</span></div></div>}</div>;
}
