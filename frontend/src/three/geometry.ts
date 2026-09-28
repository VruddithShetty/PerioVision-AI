import * as THREE from "three";
import { mergeGeometries, mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";

/**
 * Procedural molar: a lathe-turned crown with four cusps and a cervical neck (the CEJ),
 * plus two tapered, slightly curved roots. Vertices are welded so the surface shades smoothly.
 */
export function createToothGeometry(): THREE.BufferGeometry {
  const profile = [
    [0.0, 1.22], [0.18, 1.24], [0.4, 1.3], [0.6, 1.3], [0.76, 1.2], [0.86, 1.02], [0.9, 0.8], [0.88, 0.58],
    [0.8, 0.38], [0.7, 0.22], [0.64, 0.08], [0.62, 0.0],
  ].map(([x, y]) => new THREE.Vector2(x!, y!));
  const crown = new THREE.LatheGeometry(profile, 64);

  // Four cusps: lift the occlusal surface in a cos(2θ)^2 pattern, stronger toward the rim.
  const pos = crown.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const y = pos.getY(i);
    if (y > 1.1) {
      const r = Math.hypot(x, z);
      const theta = Math.atan2(z, x) + Math.PI / 4;
      const cusp = Math.pow(Math.cos(2 * theta), 2) * Math.min(1, r / 0.55);
      pos.setY(i, y + 0.14 * cusp - 0.1 * (1 - Math.min(1, r / 0.3)));
    }
  }

  const root = (offset: number, lean: number) => {
    const g = new THREE.CylinderGeometry(0.34, 0.07, 1.8, 32, 12, true);
    const p = g.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < p.count; i++) {
      const t = (0.9 - p.getY(i)) / 1.8; // 0 at the neck, 1 at the apex
      p.setX(i, p.getX(i) + lean * t * t);
      p.setZ(i, p.getZ(i) * (1 - 0.25 * t));
    }
    g.translate(offset, -0.88, 0);
    return g;
  };

  const parts = [crown, root(-0.3, -0.28), root(0.3, 0.28)].map((g) => {
    const ng = g.index ? g.toNonIndexed() : g;
    ng.deleteAttribute("uv");
    ng.deleteAttribute("normal");
    return ng;
  });
  const merged = mergeVertices(mergeGeometries(parts)!, 1e-3);
  merged.computeVertexNormals();
  merged.center();
  return merged;
}

/** Points on a U-shaped dental arch (FDI order left-to-right for one jaw). */
export function archPositions(count: number, width = 5, depth = 3.2): { x: number; z: number; angle: number }[] {
  return Array.from({ length: count }, (_, i) => {
    const t = count === 1 ? 0.5 : i / (count - 1);
    const a = Math.PI * (1 - t);
    const x = Math.cos(a) * (width / 2);
    const z = -Math.sin(a) * depth + depth * 0.4;
    return { x, z, angle: Math.atan2(x, depth) };
  });
}
