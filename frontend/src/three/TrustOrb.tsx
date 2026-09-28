import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { createToothGeometry } from "./geometry";

/** Layered "trust orb": core = model signature, rings = calibration and review. Colour shows health. */
function Layers({ verified, calibrated }: { verified: boolean; calibrated: boolean }) {
  const group = useRef<THREE.Group>(null);
  const tooth = useMemo(() => createToothGeometry(), []);
  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.children.forEach((c, i) => {
      c.rotation.y += dt * (0.15 + i * 0.1) * (i % 2 ? -1 : 1);
      c.rotation.x += dt * 0.05 * i;
    });
  });
  const core = verified ? "#22d3ee" : "#ef4444";
  const ring = calibrated ? "#2dd4bf" : "#fbbf24";
  return (
    <group ref={group}>
      <mesh geometry={tooth} scale={0.55}>
        <meshStandardMaterial color={core} emissive={core} emissiveIntensity={0.45} wireframe />
      </mesh>
      <mesh>
        <torusGeometry args={[1.5, 0.02, 8, 120]} />
        <meshBasicMaterial color={core} />
      </mesh>
      <mesh rotation={[Math.PI / 3, 0, 0]}>
        <torusGeometry args={[1.9, 0.02, 8, 120]} />
        <meshBasicMaterial color={ring} />
      </mesh>
      <mesh rotation={[-Math.PI / 3, Math.PI / 4, 0]}>
        <torusGeometry args={[2.3, 0.015, 8, 120]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

export default function TrustOrb({ verified, calibrated }: { verified: boolean; calibrated: boolean }) {
  return (
    <Canvas camera={{ position: [0, 0, 6.5], fov: 45 }} dpr={[1, 1.5]} gl={{ alpha: true }}>
      <ambientLight intensity={0.6} />
      <pointLight position={[3, 3, 5]} intensity={40} />
      <Layers verified={verified} calibrated={calibrated} />
    </Canvas>
  );
}
