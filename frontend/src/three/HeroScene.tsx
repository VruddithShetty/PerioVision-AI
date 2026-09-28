import { Float, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { createToothGeometry } from "./geometry";

function Tooth() {
  const geometry = useMemo(() => createToothGeometry(), []);
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.35;
  });
  return (
    <Float speed={1.4} rotationIntensity={0.25} floatIntensity={0.6}>
      <mesh ref={ref} geometry={geometry} scale={1.25} castShadow>
        <meshPhysicalMaterial
          color="#dff6ff"
          roughness={0.25}
          metalness={0.05}
          transmission={0.35}
          thickness={1.2}
          clearcoat={1}
          clearcoatRoughness={0.15}
          emissive="#0e7490"
          emissiveIntensity={0.18}
        />
      </mesh>
      {/* bone-level ring: where the alveolar crest would sit */}
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, -0.25, 0]}>
        <torusGeometry args={[1.25, 0.012, 8, 96]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.7} />
      </mesh>
    </Float>
  );
}

function Shield() {
  const ref = useRef<THREE.Group>(null);
  const hex = useMemo(() => {
    const shape = new THREE.Shape();
    for (let i = 0; i <= 6; i++) {
      const a = (i / 6) * Math.PI * 2 + Math.PI / 6;
      const v = [Math.cos(a) * 2.6, Math.sin(a) * 2.6] as const;
      if (i === 0) shape.moveTo(v[0], v[1]);
      else shape.lineTo(v[0], v[1]);
    }
    return new THREE.EdgesGeometry(new THREE.ShapeGeometry(shape));
  }, []);
  useFrame((_, dt) => {
    if (ref.current) {
      ref.current.rotation.z += dt * 0.08;
      ref.current.rotation.y = Math.sin(performance.now() / 3000) * 0.25;
    }
  });
  return (
    <group ref={ref}>
      <lineSegments geometry={hex}>
        <lineBasicMaterial color="#22d3ee" transparent opacity={0.55} />
      </lineSegments>
      <mesh>
        <torusGeometry args={[2.95, 0.006, 6, 160]} />
        <meshBasicMaterial color="#2dd4bf" transparent opacity={0.4} />
      </mesh>
    </group>
  );
}

function Particles({ count = 900 }: { count?: number }) {
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 3.2 + Math.random() * 4;
      const t = Math.random() * Math.PI * 2;
      const p = Math.acos(2 * Math.random() - 1);
      arr.set([r * Math.sin(p) * Math.cos(t), r * Math.cos(p) * 0.6, r * Math.sin(p) * Math.sin(t)], i * 3);
    }
    return arr;
  }, [count]);
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y -= dt * 0.03;
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.025} color="#67e8f9" transparent opacity={0.7} sizeAttenuation />
    </points>
  );
}

export default function HeroScene({ interactive = true }: { interactive?: boolean }) {
  return (
    <Canvas camera={{ position: [0, 0.6, 7], fov: 42 }} dpr={[1, 1.75]} gl={{ antialias: true, alpha: true }}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 6, 5]} intensity={1.4} color="#e0f7ff" />
      <pointLight position={[-4, -2, -3]} intensity={30} color="#14b8a6" />
      <Tooth />
      <Shield />
      <Particles />
      {interactive && <OrbitControls enableZoom={false} enablePan={false} autoRotate={false} />}
      <EffectComposer>
        <Bloom intensity={0.6} luminanceThreshold={0.35} luminanceSmoothing={0.3} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}
