import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bounds, Center, Grid, OrbitControls, useAnimations, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { api } from "./api";

type TesterStatus = { state: string; clip: string; speed: number; time: number; rootMotion: boolean; direction_degrees: number; grounded: boolean; crouched: boolean; sprinting: boolean; transition?: string | null; blend: number; rootMotionMode: string };
type RenderMode = "material" | "albedo" | "clay";

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

type GraphBlend = { action_name: string; weight: number };

function AnimatedAsset({ url, selectedClip, graphClip, graphBlend, wireframe, skeleton, renderMode, onActions, onStatus }: { url: string; selectedClip: string; graphClip: string; graphBlend: GraphBlend[]; wireframe: boolean; skeleton: boolean; renderMode: RenderMode; onActions: (names: string[]) => void; onStatus: (status: TesterStatus) => void }) {
  const root = useRef<THREE.Group>(null);
  const keys = useRef(new Set<string>());
  const activeClip = useRef("");
  const lastStatus = useRef("");
  const previousState = useRef("idle");
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
    const originals: Array<{ mesh: THREE.Mesh; material: THREE.Material | THREE.Material[] }> = [];
    const diagnostics: THREE.Material[] = [];
    asset.scene.traverse(object => {
      if (!(object as THREE.Mesh).isMesh) return;
      const mesh = object as THREE.Mesh;
      originals.push({ mesh, material: mesh.material });
      const convert = (source: THREE.Material) => {
        const pbr = source as THREE.MeshStandardMaterial;
        const material = renderMode === "albedo"
          ? new THREE.MeshBasicMaterial({ map: pbr.map, color: pbr.color, toneMapped: false })
          : renderMode === "clay"
            ? new THREE.MeshStandardMaterial({ color: "#a0a0a0", roughness: 0.85, metalness: 0 })
            : source.clone();
        material.side = source.side;
        material.transparent = source.transparent;
        material.opacity = source.opacity;
        material.alphaTest = source.alphaTest;
        if ("alphaMap" in material) material.alphaMap = pbr.alphaMap;
        if ("wireframe" in material) material.wireframe = wireframe;
        diagnostics.push(material);
        return material;
      };
      mesh.material = Array.isArray(mesh.material) ? mesh.material.map(convert) : convert(mesh.material);
    });
    return () => {
      for (const { mesh, material } of originals) mesh.material = material;
      for (const material of diagnostics) material.dispose();
    };
  }, [asset.scene, wireframe, renderMode]);
  useFrame((_, delta) => {
    const selected = chooseState(keys.current);
    const requestedBlend = selectedClip
      ? [{ action_name: selectedClip, weight: 1 }]
      : graphBlend.length
        ? graphBlend
        : [{ action_name: graphClip || findAction(actionNames, selected.state, ""), weight: 1 }];
    const resolvedBlend = requestedBlend.map(entry => ({ name: findAction(actionNames, selected.state, entry.action_name), weight: entry.weight })).filter(entry => entry.name);
    const clip = resolvedBlend[0]?.name ?? "";
    const blendKey = resolvedBlend.map(entry => `${entry.name}:${entry.weight.toFixed(4)}`).join("|");
    if (blendKey && blendKey !== activeClip.current) {
      const desired = new Set(resolvedBlend.map(entry => entry.name));
      Object.entries(actions).forEach(([name, action]) => { if (!desired.has(name)) action?.fadeOut(0.16); });
      resolvedBlend.forEach(entry => {
        const next = actions[entry.name];
        next?.reset().fadeIn(0.16).setEffectiveWeight(entry.weight).play();
      });
      activeClip.current = blendKey;
    }
    mixer.update(delta * selected.speed);
    const direction = new THREE.Vector3((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), 0, (keys.current.has("s") ? 1 : 0) - (keys.current.has("w") ? 1 : 0));
    if (direction.lengthSq() > 0 && root.current) root.current.position.addScaledVector(direction.normalize(), delta * selected.speed);
    const action = clip ? actions[clip] : undefined;
    const statusKey = `${selected.state}|${clip}|${selected.speed}`;
    if (statusKey !== lastStatus.current) { lastStatus.current = statusKey; const moving = keys.current.has("w") || keys.current.has("a") || keys.current.has("s") || keys.current.has("d"); const angle = Math.atan2((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), (keys.current.has("w") ? 1 : 0) - (keys.current.has("s") ? 1 : 0)) * 180 / Math.PI; onStatus({ state: selected.state, clip, speed: selected.speed, time: action?.time ?? 0, rootMotion: false, direction_degrees: moving ? angle : 0, grounded: !keys.current.has(" "), crouched: keys.current.has("control"), sprinting: keys.current.has("shift"), transition: null, blend: 1, rootMotionMode: "in_place" }); previousState.current = selected.state; }
  });
  return <group ref={root}><primitive object={asset.scene} />{skeleton && <primitive object={skeletonHelper} />}</group>;
}

export default function Viewport({ assetUrl, jobId, graphEnabled, equipmentType }: { assetUrl?: string; jobId?: string; graphEnabled?: boolean; equipmentType?: string | null }) {
  const [actions, setActions] = useState<string[]>([]);
  const [selectedClip, setSelectedClip] = useState("");
  const [wireframe, setWireframe] = useState(false);
  const [skeleton, setSkeleton] = useState(false);
  const [renderMode, setRenderMode] = useState<RenderMode>("material");
  const [status, setStatus] = useState<TesterStatus>({ state: "idle", clip: "", speed: 1, time: 0, rootMotion: false, direction_degrees: 0, grounded: true, crouched: false, sprinting: false, blend: 1, rootMotionMode: "in_place" });
  const [graphClip, setGraphClip] = useState("");
  const [graphBlend, setGraphBlend] = useState<GraphBlend[]>([]);
  const handleActions = useCallback((names: string[]) => { setActions(names); setSelectedClip(current => current && names.includes(current) ? current : ""); }, []);
  const handleStatus = useCallback((next: TesterStatus) => { if (jobId && graphEnabled) void api.evaluateAnimationGraph(jobId, { speed: next.speed, direction_degrees: next.direction_degrees, grounded: next.grounded, crouched: next.crouched, sprinting: next.sprinting, equipment_type: equipmentType ?? null, action: null, action_time: next.time, combo_index: 0, previous_state: status.state }).then(result => { setGraphClip(result.action_name ?? ""); setGraphBlend(result.blend_tree ?? []); setStatus({ ...next, transition: result.transition, blend: result.blend, rootMotion: result.root_motion, rootMotionMode: result.root_motion_mode }); }).catch(() => { setGraphBlend([]); setStatus(next); }); else setStatus(next); }, [equipmentType, graphEnabled, jobId, status.state]);
  return <div className="viewport-shell"><div className="viewport"><Canvas camera={{ position: [0, 0.8, -3], fov: 42 }}><color attach="background" args={["#0c0e12"]} /><ambientLight intensity={1.2} /><directionalLight position={[3, 5, 2]} intensity={2} /><Grid args={[10, 10]} cellColor="#29303a" sectionColor="#4a5666" fadeDistance={12} />{assetUrl && <Bounds key={assetUrl} fit clip observe margin={1.3}><Center top><AnimatedAsset key={assetUrl} url={assetUrl} renderMode={renderMode} selectedClip={selectedClip} graphClip={graphClip} graphBlend={graphBlend} wireframe={wireframe} skeleton={skeleton} onActions={handleActions} onStatus={handleStatus} /></Center></Bounds>}<OrbitControls makeDefault /></Canvas><div className={`viewport-empty ${assetUrl ? "has-asset" : ""}`}><span>{assetUrl ? "Validated asset" : "Unit Tester"}</span><small>{assetUrl ? "WASD move · Shift sprint · Ctrl crouch · Space jump" : "Validated GLB assets will appear here"}</small></div></div>{assetUrl && <div className="tester-toolbar"><label>View<select aria-label="Render mode" value={renderMode} onChange={event => setRenderMode(event.target.value as RenderMode)}><option value="material">Materials</option><option value="albedo">Base color</option><option value="clay">Geometry</option></select></label><label>Clip<select value={selectedClip} onChange={event => setSelectedClip(event.target.value)} disabled={!actions.length}><option value="">Graph / auto state</option>{actions.map(name => <option key={name} value={name}>{name}</option>)}</select></label><label className="debug-toggle"><input type="checkbox" checked={wireframe} onChange={event => setWireframe(event.target.checked)} /> Wireframe</label><label className="debug-toggle"><input type="checkbox" checked={skeleton} onChange={event => setSkeleton(event.target.checked)} /> Skeleton</label><div className="tester-stats"><span>{status.state}</span><span>{status.clip || "no clip"}</span><span>{status.speed.toFixed(1)}×</span><span>{status.blend.toFixed(2)} blend</span><span>{status.rootMotionMode}</span>{status.transition && <span>{status.transition}</span>}</div></div>}</div>;
}
