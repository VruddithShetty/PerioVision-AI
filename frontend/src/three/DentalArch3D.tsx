import { Html, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo, useState } from "react";
import type { Tooth } from "@/api/types";
import { stageColor } from "@/lib/format";
import { archPositions, createToothGeometry } from "./geometry";

/**
 * 3D dental arch: one procedural tooth per detected tooth, coloured by stage, sitting in a
 * translucent gum. Upper-jaw FDI numbers (1x, 2x) form the upper arch and lower (3x, 4x) the lower;
 * demo/positional IDs go on the upper arch in detection order. Clicking a tooth selects it in the 2D viewer.
 */
function sortKey(id: string): number {
  const n = Number(id);
  if (Number.isNaN(n)) return Number(id.replace(/\D/g, "")) || 0;
  const q = Math.floor(n / 10);
  const u = n % 10;
  return q === 1 || q === 4 ? -u : u; // quadrants 1 and 4 run right-to-left on screen
}

function Gum({ count, y, flip }: { count: number; y: number; flip: boolean }) {
  const pts = archPositions(Math.max(count, 2));
  return (
    <group position={[0, y + (flip ? 0.25 : -0.25), 0]}>
      {pts.map((p, i) => (
        <mesh key={i} position={[p.x, 0, p.z]} rotation={[0, -p.angle, 0]}>
          <boxGeometry args={[0.62, 0.22, 0.55]} />
          <meshStandardMaterial color="#f472b6" transparent opacity={0.16} roughness={0.8} />
        </mesh>
      ))}
    </group>
  );
}

export default function DentalArch3D({ teeth, selected, onSelect }: {
  teeth: Tooth[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const geometry = useMemo(() => createToothGeometry(), []);
  const [hover, setHover] = useState<string | null>(null);
  const { upper, lower } = useMemo(() => {
    const isLower = (t: Tooth) => /^[34]\d$/.test(t.tooth_id);
    const up = teeth.filter((t) => !isLower(t)).sort((a, b) => sortKey(a.tooth_id) - sortKey(b.tooth_id));
    const lo = teeth.filter(isLower).sort((a, b) => sortKey(a.tooth_id) - sortKey(b.tooth_id));
    return { upper: up, lower: lo };
  }, [teeth]);

  const row = (list: Tooth[], y: number, flip: boolean) =>
    archPositions(list.length).map((p, i) => {
      const t = list[i]!;
      const active = selected === t.tooth_id;
      const color = t.bone_loss_pct === null ? "#5b6f8c" : stageColor(t.stage);
      return (
        <group key={t.tooth_id} position={[p.x, y, p.z]} rotation={[flip ? Math.PI : 0, -p.angle, 0]}>
          <mesh
            geometry={geometry}
            scale={active ? 0.36 : 0.3}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(t.tooth_id);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHover(t.tooth_id);
              document.body.style.cursor = "pointer";
            }}
            onPointerOut={() => {
              setHover(null);
              document.body.style.cursor = "";
            }}
          >
            <meshPhysicalMaterial
              color={color}
              emissive={color}
              emissiveIntensity={active ? 0.55 : hover === t.tooth_id ? 0.35 : 0.1}
              roughness={0.3}
              clearcoat={0.8}
            />
          </mesh>
          {(active || hover === t.tooth_id) && (
            <Html center distanceFactor={5} position={[0, flip ? -1.1 : 1.1, 0]}>
              <div className="pointer-events-none whitespace-nowrap rounded-md border border-white/10 bg-ink-900/90 px-2 py-1 text-[11px] text-mist-100 shadow-lg">
                Tooth {t.tooth_id} · {t.bone_loss_pct === null ? "n/a" : `${t.bone_loss_pct.toFixed(0)}% bone loss`} · Stage{" "}
                {t.stage ?? "–"}
              </div>
            </Html>
          )}
        </group>
      );
    });

  return (
    <Canvas camera={{ position: [0, 3.2, 9.5], fov: 38 }} dpr={[1, 1.5]} gl={{ alpha: true }}>
      <ambientLight intensity={0.55} />
      <directionalLight position={[3, 6, 4]} intensity={1.3} />
      <pointLight position={[-4, 2, -2]} intensity={20} color="#22d3ee" />
      <group position={[0, 0, -0.5]}>
        {/* upper teeth hang crown-down, lower teeth stand crown-up, meeting at the occlusal plane */}
        {upper.length > 0 && <Gum count={upper.length} y={0.7} flip />}
        {lower.length > 0 && <Gum count={lower.length} y={-0.7} flip={false} />}
        {row(upper, 0.7, true)}
        {row(lower, -0.7, false)}
      </group>
      <OrbitControls enablePan={false} minDistance={5} maxDistance={12} />
    </Canvas>
  );
}
