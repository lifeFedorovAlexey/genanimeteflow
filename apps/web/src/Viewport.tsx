import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bounds, Center, Grid, OrbitControls, useAnimations, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { api } from "./api";

type TesterStatus = { state: string; clip: string; action?: string | null; speed: number; time: number; rootMotion: boolean; direction_degrees: number; grounded: boolean; crouched: boolean; sprinting: boolean; transition?: string | null; blend: number; rootMotionMode: string };
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

function isUpperBodyTrack(track: THREE.KeyframeTrack): boolean {
  const target = track.name.split(".")[0];
  return /(Spine|Neck|Head|Shoulder|Arm|ForeArm|Hand)/i.test(target);
}

function isActionName(name: string): boolean {
  return /(attack|punch|shoot|reload|hit|death|dance|emote|gesture|taunt)/i.test(name);
}

function DebugMarkers({ scene, showSockets, showIkTargets }: { scene: THREE.Object3D; showSockets: boolean; showIkTargets: boolean }) {
  useEffect(() => {
    const markers: THREE.Object3D[] = [];
    scene.traverse(object => {
      const name = object.name.toLowerCase();
      if (name.endsWith("__debug")) return;
      const isSocket = name.includes("socket_");
      const isIkTarget = name.includes("ik_target_");
      if (!isSocket && !isIkTarget) return;
      const marker = isSocket
        ? new THREE.AxesHelper(0.12)
        : new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 8), new THREE.MeshBasicMaterial({ color: "#f2c15e" }));
      marker.name = `${object.name}__debug`;
      object.add(marker);
      markers.push(marker);
    });
    return () => {
      markers.forEach(marker => {
        marker.parent?.remove(marker);
        const mesh = marker as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        if (Array.isArray(mesh.material)) mesh.material.forEach(material => material.dispose());
        else if (mesh.material) mesh.material.dispose();
      });
    };
  }, [scene]);
  useEffect(() => {
    scene.traverse(object => {
      const name = object.name.toLowerCase();
      if (name.includes("socket_") && object.children.length) object.children.filter(child => child.name.endsWith("__debug")).forEach(child => { child.visible = showSockets; });
      if (name.includes("ik_target_") && object.children.length) object.children.filter(child => child.name.endsWith("__debug")).forEach(child => { child.visible = showIkTargets; });
    });
  }, [scene, showIkTargets, showSockets]);
  return null;
}

function AnimatedAsset({ url, selectedClip, activeAction, upperBodyAction, graphClip, graphBlend, wireframe, skeleton, showSockets, showIkTargets, showBounds, showClothing, showEquipment, renderMode, onActions, onAction, onStatus }: { url: string; selectedClip: string; activeAction: string; upperBodyAction: string; graphClip: string; graphBlend: GraphBlend[]; wireframe: boolean; skeleton: boolean; showSockets: boolean; showIkTargets: boolean; showBounds: boolean; showClothing: boolean; showEquipment: boolean; renderMode: RenderMode; onActions: (names: string[]) => void; onAction: (name: string) => void; onStatus: (status: TesterStatus) => void }) {
  const root = useRef<THREE.Group>(null);
  const keys = useRef(new Set<string>());
  const activeClip = useRef("");
  const activeUpperClip = useRef("");
  const lastStatus = useRef("");
  const previousState = useRef("idle");
  const asset = useGLTF(url);
  const { actions, mixer } = useAnimations(asset.animations, root);
  const actionNames = useMemo(() => asset.animations.map(animation => animation.name).filter(Boolean), [asset.animations]);
  const upperActions = useRef<Record<string, THREE.AnimationAction>>({});
  const upperClips = useMemo(() => {
    const masked: Record<string, THREE.AnimationClip> = {};
    asset.animations.forEach(animation => {
      const tracks = animation.tracks.filter(isUpperBodyTrack);
      if (tracks.length === 0) return;
      masked[animation.name] = new THREE.AnimationClip(`${animation.name}__upper_body`, animation.duration, tracks);
    });
    return masked;
  }, [asset.animations]);
  useEffect(() => {
    const sceneRoot = root.current ?? asset.scene;
    const actionsForClips: Record<string, THREE.AnimationAction> = {};
    Object.entries(upperClips).forEach(([name, clip]) => {
      actionsForClips[name] = mixer.clipAction(clip, sceneRoot);
    });
    upperActions.current = actionsForClips;
    return () => {
      Object.values(actionsForClips).forEach(action => {
        action.stop();
        mixer.uncacheAction(action.getClip(), sceneRoot);
      });
      upperActions.current = {};
    };
  }, [asset.scene, mixer, upperClips]);
  const skeletonHelper = useMemo(() => new THREE.SkeletonHelper(asset.scene), [asset.scene]);

  useEffect(() => { onActions(actionNames); }, [actionNames, onActions]);
  useEffect(() => {
    const actionCandidates = () => actionNames.filter(isActionName);
    const pick = (pattern: RegExp, fallbackIndex: number) => actionCandidates().find(name => pattern.test(name)) ?? actionCandidates()[fallbackIndex] ?? "";
    const down = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      if ([" ", "shift", "control", "w", "a", "s", "d"].includes(key)) { event.preventDefault(); keys.current.add(key); return; }
      if (key === "1") onAction(pick(/attack|punch|shoot/i, 0));
      if (key === "2") onAction(pick(/attack|punch|shoot|reload/i, 1));
      if (key === "3") onAction(pick(/hit/i, 0));
      if (key === "4") onAction(pick(/death/i, 0));
      if (key === "q" || key === "e") {
        const candidates = actionCandidates();
        if (candidates.length) {
          const current = Math.max(0, candidates.indexOf(activeAction));
          onAction(candidates[(current + (key === "q" ? candidates.length - 1 : 1)) % candidates.length]);
        }
      }
    };
    const up = (event: KeyboardEvent) => keys.current.delete(event.key.toLowerCase());
    window.addEventListener("keydown", down); window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, [actionNames, activeAction, onAction]);
  useEffect(() => {
    const originals: Array<{ mesh: THREE.Mesh; material: THREE.Material | THREE.Material[] }> = [];
    const diagnostics: THREE.Material[] = [];
    asset.scene.traverse(object => {
      const objectName = object.name.toLowerCase();
      if (objectName.includes("clothing_") || objectName.includes("vest")) object.visible = showClothing;
      if (objectName.includes("rifle") || objectName.includes("weapon") || objectName.includes("sword")) object.visible = showEquipment;
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
  }, [asset.scene, showClothing, showEquipment, wireframe, renderMode]);
  const boundsHelper = useMemo(() => new THREE.BoxHelper(asset.scene, "#82a4ff"), [asset.scene]);
  useFrame(() => boundsHelper.update());
  useFrame((_, delta) => {
    const selected = chooseState(keys.current);
    const requestedBlend = activeAction
      ? [{ action_name: activeAction, weight: 1 }]
      : selectedClip
      ? [{ action_name: selectedClip, weight: 1 }]
      : graphBlend.length
        ? graphBlend
        : [{ action_name: graphClip || findAction(actionNames, selected.state, ""), weight: 1 }];
    const resolvedBlend = requestedBlend.map(entry => ({ name: findAction(actionNames, selected.state, entry.action_name), weight: entry.weight })).filter(entry => entry.name);
    const clip = resolvedBlend[0]?.name ?? "";
    const upperClip = upperBodyAction ? findAction(actionNames, selected.state, upperBodyAction) : "";
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
    if (upperClip !== activeUpperClip.current) {
      if (activeUpperClip.current) upperActions.current[activeUpperClip.current]?.fadeOut(0.12);
      if (upperClip) upperActions.current[upperClip]?.reset().fadeIn(0.12).setEffectiveWeight(1).play();
      activeUpperClip.current = upperClip;
    }
    mixer.update(delta * selected.speed);
    const direction = new THREE.Vector3((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), 0, (keys.current.has("s") ? 1 : 0) - (keys.current.has("w") ? 1 : 0));
    if (direction.lengthSq() > 0 && root.current) root.current.position.addScaledVector(direction.normalize(), delta * selected.speed);
    const action = clip ? actions[clip] : undefined;
    const statusKey = `${selected.state}|${clip}|${activeAction}|${upperClip}|${selected.speed}`;
    if (statusKey !== lastStatus.current) { lastStatus.current = statusKey; const moving = keys.current.has("w") || keys.current.has("a") || keys.current.has("s") || keys.current.has("d"); const angle = Math.atan2((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), (keys.current.has("w") ? 1 : 0) - (keys.current.has("s") ? 1 : 0)) * 180 / Math.PI; onStatus({ state: selected.state, clip, action: activeAction || null, speed: selected.speed, time: action?.time ?? 0, rootMotion: false, direction_degrees: moving ? angle : 0, grounded: !keys.current.has(" "), crouched: keys.current.has("control"), sprinting: keys.current.has("shift"), transition: null, blend: 1, rootMotionMode: "in_place" }); previousState.current = selected.state; }
  });
  return <group ref={root}><primitive object={asset.scene} /><DebugMarkers scene={asset.scene} showSockets={showSockets} showIkTargets={showIkTargets} />{skeleton && <primitive object={skeletonHelper} />}<primitive object={boundsHelper} visible={showBounds} /></group>;
}

export default function Viewport({ assetUrl, jobId, graphEnabled, equipmentType }: { assetUrl?: string; jobId?: string; graphEnabled?: boolean; equipmentType?: string | null }) {
  const [actions, setActions] = useState<string[]>([]);
  const [selectedClip, setSelectedClip] = useState("");
  const [activeAction, setActiveAction] = useState("");
  const [upperBodyAction, setUpperBodyAction] = useState("");
  const [wireframe, setWireframe] = useState(false);
  const [skeleton, setSkeleton] = useState(false);
  const [showSockets, setShowSockets] = useState(false);
  const [showIkTargets, setShowIkTargets] = useState(false);
  const [showBounds, setShowBounds] = useState(false);
  const [showClothing, setShowClothing] = useState(true);
  const [showEquipment, setShowEquipment] = useState(true);
  const [renderMode, setRenderMode] = useState<RenderMode>("material");
  const [status, setStatus] = useState<TesterStatus>({ state: "idle", clip: "", speed: 1, time: 0, rootMotion: false, direction_degrees: 0, grounded: true, crouched: false, sprinting: false, blend: 1, rootMotionMode: "in_place" });
  const [graphClip, setGraphClip] = useState("");
  const [graphBlend, setGraphBlend] = useState<GraphBlend[]>([]);
  const handleActions = useCallback((names: string[]) => { setActions(names); setSelectedClip(current => current && names.includes(current) ? current : ""); setActiveAction(current => current && names.includes(current) ? current : ""); setUpperBodyAction(current => current && names.includes(current) ? current : ""); }, []);
  const handleAction = useCallback((name: string) => { setActiveAction(name); setSelectedClip(""); }, []);
  const handleStatus = useCallback((next: TesterStatus) => { if (jobId && graphEnabled) void api.evaluateAnimationGraph(jobId, { speed: next.speed, direction_degrees: next.direction_degrees, grounded: next.grounded, crouched: next.crouched, sprinting: next.sprinting, equipment_type: equipmentType ?? null, action: next.action ?? null, action_time: next.time, combo_index: 0, previous_state: status.state, upper_body_action: upperBodyAction || null }).then(result => { setGraphClip(result.action_name ?? ""); setGraphBlend(result.blend_tree ?? []); setStatus({ ...next, transition: result.transition, blend: result.blend, rootMotion: result.root_motion, rootMotionMode: result.root_motion_mode }); }).catch(() => { setGraphBlend([]); setStatus(next); }); else setStatus(next); }, [equipmentType, graphEnabled, jobId, status.state, upperBodyAction]);
  const actionNames = useMemo(() => actions.filter(isActionName), [actions]);
  return <div className="viewport-shell"><div className="viewport"><Canvas camera={{ position: [0, 0.8, -3], fov: 42 }}><color attach="background" args={["#0c0e12"]} /><ambientLight intensity={1.2} /><directionalLight position={[3, 5, 2]} intensity={2} /><Grid args={[10, 10]} cellColor="#29303a" sectionColor="#4a5666" fadeDistance={12} />{assetUrl && <Bounds key={assetUrl} fit clip observe margin={1.3}><Center top><AnimatedAsset key={assetUrl} url={assetUrl} renderMode={renderMode} selectedClip={selectedClip} activeAction={activeAction} upperBodyAction={upperBodyAction} graphClip={graphClip} graphBlend={graphBlend} wireframe={wireframe} skeleton={skeleton} showSockets={showSockets} showIkTargets={showIkTargets} showBounds={showBounds} showClothing={showClothing} showEquipment={showEquipment} onActions={handleActions} onAction={handleAction} onStatus={handleStatus} /></Center></Bounds>}<OrbitControls makeDefault /></Canvas><div className={`viewport-empty ${assetUrl ? "has-asset" : ""}`}><span>{assetUrl ? "Validated asset" : "Unit Tester"}</span><small>{assetUrl ? "WASD move · Shift sprint · Ctrl crouch · Space jump" : "Validated GLB assets will appear here"}</small></div></div>{assetUrl && <div className="tester-toolbar"><label>View<select aria-label="Render mode" value={renderMode} onChange={event => setRenderMode(event.target.value as RenderMode)}><option value="material">Materials</option><option value="albedo">Base color</option><option value="clay">Geometry</option></select></label><label>Clip<select value={selectedClip} onChange={event => { setSelectedClip(event.target.value); setActiveAction(""); }} disabled={!actions.length}><option value="">Graph / auto state</option>{actions.map(name => <option key={name} value={name}>{name}</option>)}</select></label><label>Upper body<select aria-label="Upper body action" value={upperBodyAction} onChange={event => setUpperBodyAction(event.target.value)} disabled={!actions.length}><option value="">None</option>{actions.map(name => <option key={name} value={name}>{name}</option>)}</select></label><div className="action-buttons"><button className="debug-toggle" onClick={() => handleAction(actionNames[0] ?? "")} disabled={!actionNames.length}>1 Attack</button><button className="debug-toggle" onClick={() => handleAction(actionNames[1] ?? actionNames[0] ?? "")} disabled={!actionNames.length}>2 Alt</button><button className="debug-toggle" onClick={() => handleAction(actionNames.find(name => /hit/i.test(name)) ?? "")} disabled={!actionNames.some(name => /hit/i.test(name))}>3 Hit</button><button className="debug-toggle" onClick={() => handleAction(actionNames.find(name => /death/i.test(name)) ?? "")} disabled={!actionNames.some(name => /death/i.test(name))}>4 Death</button><button className="debug-toggle" onClick={() => setActiveAction("")}>Clear action</button></div><label className="debug-toggle"><input type="checkbox" checked={wireframe} onChange={event => setWireframe(event.target.checked)} /> Wireframe</label><label className="debug-toggle"><input type="checkbox" checked={skeleton} onChange={event => setSkeleton(event.target.checked)} /> Skeleton</label><label className="debug-toggle"><input type="checkbox" checked={showSockets} onChange={event => setShowSockets(event.target.checked)} /> Sockets</label><label className="debug-toggle"><input type="checkbox" checked={showIkTargets} onChange={event => setShowIkTargets(event.target.checked)} /> IK targets</label><label className="debug-toggle"><input type="checkbox" checked={showBounds} onChange={event => setShowBounds(event.target.checked)} /> Bounds</label><label className="debug-toggle"><input type="checkbox" checked={showClothing} onChange={event => setShowClothing(event.target.checked)} /> Clothing</label><label className="debug-toggle"><input type="checkbox" checked={showEquipment} onChange={event => setShowEquipment(event.target.checked)} /> Equipment</label><div className="tester-stats"><span>{status.state}</span><span>{status.clip || "no clip"}</span><span>{activeAction ? `action:${activeAction}` : "action:none"}</span><span>{upperBodyAction ? `upper:${upperBodyAction}` : "upper:none"}</span><span>{status.speed.toFixed(1)}×</span><span>{status.blend.toFixed(2)} blend</span><span>{status.rootMotionMode}</span>{status.transition && <span>{status.transition}</span>}</div></div>}</div>;
}
