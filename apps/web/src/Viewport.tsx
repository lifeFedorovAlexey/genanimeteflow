import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bounds, Center, Grid, OrbitControls, useAnimations, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { api } from "./api";

type TesterStatus = { state: string; clip: string; action?: string | null; speed: number; time: number; rootMotion: boolean; direction_degrees: number; grounded: boolean; crouched: boolean; sprinting: boolean; transition?: string | null; blend: number; rootMotionMode: string };
type RenderMode = "material" | "albedo" | "clay";
type ActionBindingName = "primary" | "secondary" | "hit" | "death" | "previous" | "next";
type ActionBindings = Record<ActionBindingName, string>;
const DEFAULT_BINDINGS: ActionBindings = { primary: "1", secondary: "2", hit: "3", death: "4", previous: "q", next: "e" };

function eventKey(value: string): string {
  return value === " " ? "space" : value.toLowerCase();
}

function displayKey(value: string): string {
  return value === "space" ? "Space" : value.length === 1 ? value.toUpperCase() : value;
}

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
      if (name.includes("__debug")) return;
      const isSocket = name.includes("socket_");
      const isIkTarget = name.includes("ik_target_");
      if (!isSocket && !isIkTarget) return;
      const marker = isSocket
        ? new THREE.AxesHelper(0.12)
        : new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 8), new THREE.MeshBasicMaterial({ color: "#f2c15e" }));
      marker.name = `${object.name}__debug`;
      marker.visible = isSocket ? showSockets : showIkTargets;
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

function BoneMarkers({ scene, visible }: { scene: THREE.Object3D; visible: boolean }) {
  useEffect(() => {
    const markers: THREE.Mesh[] = [];
    scene.traverse(object => {
      if (!(object as THREE.Bone).isBone || object.name.includes("__debug")) return;
      const marker = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 6), new THREE.MeshBasicMaterial({ color: "#ff77c8" }));
      marker.name = `${object.name}__bones_debug`;
      object.add(marker);
      markers.push(marker);
    });
    return () => markers.forEach(marker => { marker.parent?.remove(marker); marker.geometry.dispose(); (marker.material as THREE.Material).dispose(); });
  }, [scene]);
  useEffect(() => {
    scene.traverse(object => { if (object.name.endsWith("__bones_debug")) object.visible = visible; });
  }, [scene, visible]);
  return null;
}

function NormalMarkers({ scene, visible }: { scene: THREE.Object3D; visible: boolean }) {
  useEffect(() => {
    const overlays: THREE.LineSegments[] = [];
    scene.traverse(object => {
      if (!(object as THREE.Mesh).isMesh || object.name.includes("__debug")) return;
      const mesh = object as THREE.Mesh;
      const position = mesh.geometry.getAttribute("position");
      const normal = mesh.geometry.getAttribute("normal");
      if (!position || !normal) return;
      const step = Math.max(1, Math.ceil(position.count / 1200));
      const points: number[] = [];
      const start = new THREE.Vector3();
      const end = new THREE.Vector3();
      for (let index = 0; index < position.count; index += step) {
        start.fromBufferAttribute(position, index);
        end.copy(start).addScaledVector(new THREE.Vector3().fromBufferAttribute(normal, index).normalize(), 0.055);
        points.push(start.x, start.y, start.z, end.x, end.y, end.z);
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
      const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: "#72d8ff" }));
      lines.name = `${object.name}__normals_debug`;
      lines.visible = visible;
      lines.frustumCulled = false;
      object.add(lines);
      overlays.push(lines);
    });
    return () => overlays.forEach(lines => { lines.parent?.remove(lines); lines.geometry.dispose(); (lines.material as THREE.Material).dispose(); });
  }, [scene]);
  useEffect(() => {
    scene.traverse(object => { if (object.name.endsWith("__normals_debug")) object.visible = visible; });
  }, [scene, visible]);
  return null;
}

function AnimatedAsset({ url, selectedClip, activeAction, upperBodyAction, graphClip, graphBlend, rootMotionApply, wireframe, skeleton, showBones, showNormals, showSockets, showIkTargets, showBounds, showBody, showClothing, showEquipment, renderMode, bindings, onActions, onAction, onStatus }: { url: string; selectedClip: string; activeAction: string; upperBodyAction: string; graphClip: string; graphBlend: GraphBlend[]; rootMotionApply: boolean; wireframe: boolean; skeleton: boolean; showBones: boolean; showNormals: boolean; showSockets: boolean; showIkTargets: boolean; showBounds: boolean; showBody: boolean; showClothing: boolean; showEquipment: boolean; renderMode: RenderMode; bindings: ActionBindings; onActions: (names: string[]) => void; onAction: (name: string) => void; onStatus: (status: TesterStatus) => void }) {
  const root = useRef<THREE.Group>(null);
  const keys = useRef(new Set<string>());
  const activeClip = useRef("");
  const activeUpperClip = useRef("");
  const lastStatus = useRef("");
  const previousState = useRef("idle");
  const previousRootPosition = useRef(new THREE.Vector3());
  const rootMotionClip = useRef("");
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
  const rootMotionBone = useMemo<THREE.Object3D | null>(() => {
    let candidate: THREE.Object3D | null = null;
    asset.scene.traverse(object => { if (!candidate && object.name.toLowerCase() === "root") candidate = object; });
    return candidate;
  }, [asset.scene]);

  useEffect(() => { onActions(actionNames); }, [actionNames, onActions]);
  useEffect(() => {
    const actionCandidates = () => actionNames.filter(isActionName);
    const pick = (pattern: RegExp, fallbackIndex: number) => actionCandidates().find(name => pattern.test(name)) ?? actionCandidates()[fallbackIndex] ?? "";
    const down = (event: KeyboardEvent) => {
      const key = eventKey(event.key);
      if (["space", "shift", "control", "w", "a", "s", "d"].includes(key)) { event.preventDefault(); keys.current.add(key === "space" ? " " : key); return; }
      if (key === bindings.primary) onAction(pick(/attack|punch|shoot/i, 0));
      if (key === bindings.secondary) onAction(pick(/attack|punch|shoot|reload/i, 1));
      if (key === bindings.hit) onAction(pick(/hit/i, 0));
      if (key === bindings.death) onAction(pick(/death/i, 0));
      if (key === bindings.previous || key === bindings.next) {
        const candidates = actionCandidates();
        if (candidates.length) {
          const current = Math.max(0, candidates.indexOf(activeAction));
          onAction(candidates[(current + (key === bindings.previous ? candidates.length - 1 : 1)) % candidates.length]);
        }
      }
    };
    const up = (event: KeyboardEvent) => keys.current.delete(eventKey(event.key) === "space" ? " " : eventKey(event.key));
    window.addEventListener("keydown", down); window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, [actionNames, activeAction, bindings, onAction]);
  useEffect(() => {
    const originals: Array<{ mesh: THREE.Mesh; material: THREE.Material | THREE.Material[]; visible: boolean }> = [];
    const diagnostics: THREE.Material[] = [];
    asset.scene.traverse(object => {
      const objectName = object.name.toLowerCase();
      const isClothing = objectName.includes("clothing_") || objectName.includes("vest");
      const isEquipment = objectName.includes("rifle") || objectName.includes("weapon") || objectName.includes("sword");
      if (!(object as THREE.Mesh).isMesh) return;
      const mesh = object as THREE.Mesh;
      originals.push({ mesh, material: mesh.material, visible: mesh.visible });
      mesh.visible = isClothing ? showClothing : isEquipment ? showEquipment : showBody;
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
      for (const { mesh, material, visible } of originals) { mesh.material = material; mesh.visible = visible; }
      for (const material of diagnostics) material.dispose();
    };
  }, [asset.scene, showBody, showClothing, showEquipment, wireframe, renderMode]);
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
    if (rootMotionApply && rootMotionBone && root.current) {
      const currentRootPosition = rootMotionBone.position;
      if (rootMotionClip.current !== clip) {
        rootMotionClip.current = clip;
        previousRootPosition.current.copy(currentRootPosition);
      } else {
        const rootDelta = currentRootPosition.clone().sub(previousRootPosition.current);
        root.current.position.add(rootDelta);
        rootMotionBone.position.copy(previousRootPosition.current);
        previousRootPosition.current.copy(currentRootPosition);
      }
    } else {
      rootMotionClip.current = "";
      if (rootMotionBone) previousRootPosition.current.copy(rootMotionBone.position);
      if (direction.lengthSq() > 0 && root.current) root.current.position.addScaledVector(direction.normalize(), delta * selected.speed);
    }
    const action = clip ? actions[clip] : undefined;
    const statusKey = `${selected.state}|${clip}|${activeAction}|${upperClip}|${selected.speed}`;
    if (statusKey !== lastStatus.current) { lastStatus.current = statusKey; const moving = keys.current.has("w") || keys.current.has("a") || keys.current.has("s") || keys.current.has("d"); const angle = Math.atan2((keys.current.has("d") ? 1 : 0) - (keys.current.has("a") ? 1 : 0), (keys.current.has("w") ? 1 : 0) - (keys.current.has("s") ? 1 : 0)) * 180 / Math.PI; onStatus({ state: selected.state, clip, action: activeAction || null, speed: selected.speed, time: action?.time ?? 0, rootMotion: false, direction_degrees: moving ? angle : 0, grounded: !keys.current.has(" "), crouched: keys.current.has("control"), sprinting: keys.current.has("shift"), transition: null, blend: 1, rootMotionMode: "in_place" }); previousState.current = selected.state; }
  });
  return <group ref={root}><primitive object={asset.scene} /><DebugMarkers scene={asset.scene} showSockets={showSockets} showIkTargets={showIkTargets} /><BoneMarkers scene={asset.scene} visible={showBones} /><NormalMarkers scene={asset.scene} visible={showNormals} />{skeleton && <primitive object={skeletonHelper} />}<primitive object={boundsHelper} visible={showBounds} /></group>;
}

export default function Viewport({ assetUrl, jobId, graphEnabled, equipmentType }: { assetUrl?: string; jobId?: string; graphEnabled?: boolean; equipmentType?: string | null }) {
  const [actions, setActions] = useState<string[]>([]);
  const [selectedClip, setSelectedClip] = useState("");
  const [activeAction, setActiveAction] = useState("");
  const [upperBodyAction, setUpperBodyAction] = useState("");
  const [wireframe, setWireframe] = useState(false);
  const [skeleton, setSkeleton] = useState(false);
  const [showBones, setShowBones] = useState(false);
  const [showNormals, setShowNormals] = useState(false);
  const [showSockets, setShowSockets] = useState(false);
  const [showIkTargets, setShowIkTargets] = useState(false);
  const [showBounds, setShowBounds] = useState(false);
  const [showBody, setShowBody] = useState(true);
  const [showClothing, setShowClothing] = useState(true);
  const [showEquipment, setShowEquipment] = useState(true);
  const [renderMode, setRenderMode] = useState<RenderMode>("material");
  const resetDiagnostics = useCallback(() => {
    setWireframe(false);
    setSkeleton(false);
    setShowBones(false);
    setShowNormals(false);
    setShowSockets(false);
    setShowIkTargets(false);
    setShowBounds(false);
    setRenderMode("material");
  }, []);
  const [status, setStatus] = useState<TesterStatus>({ state: "idle", clip: "", speed: 1, time: 0, rootMotion: false, direction_degrees: 0, grounded: true, crouched: false, sprinting: false, blend: 1, rootMotionMode: "in_place" });
  const [graphClip, setGraphClip] = useState("");
  const [graphBlend, setGraphBlend] = useState<GraphBlend[]>([]);
  const [rootMotionApply, setRootMotionApply] = useState(false);
  const [bindings, setBindings] = useState<ActionBindings>(DEFAULT_BINDINGS);
  const [capturingBinding, setCapturingBinding] = useState<ActionBindingName | null>(null);
  const handleActions = useCallback((names: string[]) => { setActions(names); setSelectedClip(current => current && names.includes(current) ? current : ""); setActiveAction(current => current && names.includes(current) ? current : ""); setUpperBodyAction(current => current && names.includes(current) ? current : ""); }, []);
  const handleAction = useCallback((name: string) => { setActiveAction(name); setSelectedClip(""); }, []);
  const handleStatus = useCallback((next: TesterStatus) => { if (jobId && graphEnabled) void api.evaluateAnimationGraph(jobId, { speed: next.speed, direction_degrees: next.direction_degrees, grounded: next.grounded, crouched: next.crouched, sprinting: next.sprinting, equipment_type: equipmentType ?? null, action: next.action ?? null, action_time: next.time, combo_index: 0, previous_state: status.state, upper_body_action: upperBodyAction || null }).then(result => { setGraphClip(result.action_name ?? ""); setGraphBlend(result.blend_tree ?? []); setRootMotionApply(Boolean(result.root_motion)); setStatus({ ...next, transition: result.transition, blend: result.blend, rootMotion: result.root_motion, rootMotionMode: result.root_motion_mode }); }).catch(() => { setGraphBlend([]); setRootMotionApply(false); setStatus(next); }); else { setRootMotionApply(false); setStatus(next); } }, [equipmentType, graphEnabled, jobId, status.state, upperBodyAction]);
  const actionNames = useMemo(() => actions.filter(isActionName), [actions]);
  const captureKey = (event: ReactKeyboardEvent<HTMLButtonElement>) => { if (!capturingBinding) return; event.preventDefault(); event.stopPropagation(); if (event.key === "Escape") { setCapturingBinding(null); return; } setBindings(current => ({ ...current, [capturingBinding]: eventKey(event.key) })); setCapturingBinding(null); };
  const bindingRows: Array<[ActionBindingName, string]> = [["primary", "Primary attack"], ["secondary", "Secondary action"], ["hit", "Hit"], ["death", "Death"], ["previous", "Previous action"], ["next", "Next action"]];
  return <div className="viewport-shell"><div className="viewport"><Canvas camera={{ position: [0, 0.8, -3], fov: 42 }}><color attach="background" args={["#0c0e12"]} /><ambientLight intensity={1.2} /><directionalLight position={[3, 5, 2]} intensity={2} /><Grid args={[10, 10]} cellColor="#29303a" sectionColor="#4a5666" fadeDistance={12} />{assetUrl && <Bounds key={assetUrl} fit clip observe margin={1.3}><Center top><AnimatedAsset key={assetUrl} url={assetUrl} renderMode={renderMode} selectedClip={selectedClip} activeAction={activeAction} upperBodyAction={upperBodyAction} graphClip={graphClip} graphBlend={graphBlend} rootMotionApply={rootMotionApply} wireframe={wireframe} skeleton={skeleton} showBones={showBones} showNormals={showNormals} showSockets={showSockets} showIkTargets={showIkTargets} showBounds={showBounds} showBody={showBody} showClothing={showClothing} showEquipment={showEquipment} bindings={bindings} onActions={handleActions} onAction={handleAction} onStatus={handleStatus} /></Center></Bounds>}<OrbitControls makeDefault /></Canvas><div className={`viewport-empty ${assetUrl ? "has-asset" : ""}`}><span>{assetUrl ? "Чистый просмотр" : "Unit Tester"}</span><small>{assetUrl ? "Персонаж без диагностических слоёв · WASD для движения" : "Проверенный GLB появится здесь"}</small></div></div>{assetUrl && <div className="tester-toolbar"><label>Просмотр<select aria-label="Режим просмотра" value={renderMode} onChange={event => setRenderMode(event.target.value as RenderMode)}><option value="material">Материалы</option><option value="albedo">Цвет текстур</option><option value="clay">Геометрия</option></select></label><label>Действие<select aria-label="Действие" value={selectedClip} onChange={event => { setSelectedClip(event.target.value); setActiveAction(""); }} disabled={!actions.length}><option value="">Автограф</option>{actions.map(name => <option key={name} value={name}>{name}</option>)}</select></label><div className="action-buttons"><button className="debug-toggle" onClick={() => handleAction(actionNames[0] ?? "")} disabled={!actionNames.length}>{displayKey(bindings.primary)} Атака</button><button className="debug-toggle" onClick={() => handleAction(actionNames[1] ?? actionNames[0] ?? "")} disabled={!actionNames.length}>{displayKey(bindings.secondary)} Альт.</button><button className="debug-toggle" onClick={() => setActiveAction("")}>Сбросить действие</button></div><details className="binding-settings"><summary>Клавиши и верх тела</summary><div className="binding-grid"><label>Верх тела<select aria-label="Действие верхней части тела" value={upperBodyAction} onChange={event => setUpperBodyAction(event.target.value)} disabled={!actions.length}><option value="">Нет</option>{actions.map(name => <option key={name} value={name}>{name}</option>)}</select></label>{bindingRows.map(([name, label]) => <button key={name} onClick={() => setCapturingBinding(name)} onKeyDown={captureKey} className={capturingBinding === name ? "capturing" : ""} aria-label={`${label}: ${displayKey(bindings[name])}`}>{label}<kbd>{capturingBinding === name ? "нажмите клавишу" : displayKey(bindings[name])}</kbd></button>)}</div></details><details className="binding-settings diagnostics-settings"><summary>Диагностика меша</summary><div className="diagnostic-actions"><button className="secondary" onClick={resetDiagnostics}>Вернуть чистый вид</button><label className="debug-toggle"><input type="checkbox" checked={wireframe} onChange={event => setWireframe(event.target.checked)} /> Сетка</label><label className="debug-toggle"><input type="checkbox" checked={skeleton} onChange={event => setSkeleton(event.target.checked)} /> Скелет</label><label className="debug-toggle"><input type="checkbox" checked={showBones} onChange={event => setShowBones(event.target.checked)} /> Точки костей</label><label className="debug-toggle"><input type="checkbox" checked={showNormals} onChange={event => setShowNormals(event.target.checked)} /> Нормали</label><label className="debug-toggle"><input type="checkbox" checked={showSockets} onChange={event => setShowSockets(event.target.checked)} /> Сокеты</label><label className="debug-toggle"><input type="checkbox" checked={showIkTargets} onChange={event => setShowIkTargets(event.target.checked)} /> IK-точки</label><label className="debug-toggle"><input type="checkbox" checked={showBounds} onChange={event => setShowBounds(event.target.checked)} /> Габариты</label><label className="debug-toggle"><input type="checkbox" checked={showBody} onChange={event => setShowBody(event.target.checked)} /> Тело</label><label className="debug-toggle"><input type="checkbox" checked={showClothing} onChange={event => setShowClothing(event.target.checked)} /> Одежда</label><label className="debug-toggle"><input type="checkbox" checked={showEquipment} onChange={event => setShowEquipment(event.target.checked)} /> Экипировка</label></div></details><div className="tester-stats"><span>{status.state}</span><span>{status.clip || "без клипа"}</span><span>{activeAction ? `действие:${activeAction}` : "действие:нет"}</span><span>{status.speed.toFixed(1)}×</span><span>{status.rootMotionMode}</span>{status.transition && <span>{status.transition}</span>}</div></div>}</div>;
}
