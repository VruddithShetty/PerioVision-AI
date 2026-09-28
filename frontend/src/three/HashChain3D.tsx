import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { AuditEntry } from "@/api/types";

/** Audit-log entries as linked blocks. Blocks at or after the first tampered entry turn red. */
function Block({ entry, index, broken }: { entry: AuditEntry; index: number; broken: boolean }) {
  const ref = useRef<THREE.Group>(null);
  const edges = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(1.02, 1.02, 1.02)), []);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.position.y = Math.sin(clock.elapsedTime * 1.2 + index * 0.6) * 0.08;
  });
  const color = broken ? "#ef4444" : "#22d3ee";
  return (
    <group position={[index * 1.6, 0, 0]}>
      <group ref={ref}>
        <mesh>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial
            color={broken ? "#3b0d0d" : "#0a1f33"}
            emissive={color}
            emissiveIntensity={0.35}
            transparent
            opacity={0.9}
          />
        </mesh>
        <lineSegments geometry={edges}>
          <lineBasicMaterial color={color} />
        </lineSegments>
      </group>
      <Html center position={[0, -0.95, 0]} distanceFactor={8}>
        <div className="pointer-events-none whitespace-nowrap text-center font-mono text-[10px] text-mist-300">
          #{entry.seq}
          <br />
          <span className={broken ? "text-critical-400" : "text-brand-300"}>{entry.entry_hash.slice(0, 8)}</span>
        </div>
      </Html>
      {index > 0 && (
        <mesh position={[-0.8, 0, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.03, 0.03, 0.6, 8]} />
          <meshBasicMaterial color={broken ? "#ef4444" : "#2dd4bf"} />
        </mesh>
      )}
    </group>
  );
}

export default function HashChain3D({ entries, firstTampered }: { entries: AuditEntry[]; firstTampered: number | null }) {
  const ordered = [...entries].sort((a, b) => a.seq - b.seq).slice(-10);
  const center = ((ordered.length - 1) * 1.6) / 2;
  return (
    <Canvas camera={{ position: [0, 0.8, 6.5], fov: 50 }} dpr={[1, 1.5]} gl={{ alpha: true }}>
      <ambientLight intensity={0.7} />
      <pointLight position={[0, 4, 6]} intensity={40} color="#67e8f9" />
      <group position={[-center, 0, 0]}>
        {ordered.map((e, i) => (
          <Block key={e.seq} entry={e} index={i} broken={firstTampered !== null && e.seq >= firstTampered} />
        ))}
      </group>
      <OrbitControls enablePan={false} enableZoom={false} />
    </Canvas>
  );
}
