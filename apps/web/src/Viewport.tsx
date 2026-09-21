import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid, OrbitControls, useGLTF } from "@react-three/drei";

function LoadedAsset({ url }: { url: string }) {
  const asset = useGLTF(url);
  return <primitive object={asset.scene} />;
}

export default function Viewport({ assetUrl }: { assetUrl?: string }) {
  return <div className="viewport"><Canvas camera={{ position: [3, 2.2, 4], fov: 42 }}><color attach="background" args={["#0c0e12"]} /><ambientLight intensity={1.2} /><directionalLight position={[3, 5, 2]} intensity={2} /><Grid args={[10, 10]} cellColor="#29303a" sectionColor="#4a5666" fadeDistance={12} />{assetUrl && <Suspense fallback={null}><LoadedAsset url={assetUrl} /></Suspense>}<OrbitControls makeDefault /></Canvas><div className={`viewport-empty ${assetUrl ? "has-asset" : ""}`}><span>{assetUrl ? "Validated asset" : "Unit Tester"}</span><small>{assetUrl ? "Orbit / zoom / pan" : "Validated GLB assets will appear here"}</small></div></div>;
}
