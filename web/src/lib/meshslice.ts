/**
 * Circumference where a cutting plane meets the limb SURFACE — leg-scan-measure's
 * method (static/meshops.js: slicePlane + circumferenceOnPlane), ported to TS.
 *
 * The plane is intersected with every triangle it crosses. Intersection points
 * are keyed by mesh edge, so neighbouring triangles share them and the segments
 * chain into exact loops. Of those loops the longest closed one is the limb.
 *
 *   tape    = convex hull perimeter in the plane — what a tape measure reads,
 *             insensitive to small dents and scan noise
 *   contour = exact outline length
 *   area    = cross-section area (closed loops only)
 *
 * This is the same computation Stage 7 runs (pipeline/core/legscan.py), on the
 * same uncut surface, so the number shown while the plane is dragged is the one
 * the result screen will report.
 *
 * Scene space is centimetres (usePly scales by cm/unit), so no scale appears here.
 */

export interface MeshSection {
  ok: true;
  kind: "mesh";
  tapeCm: number;
  contourCm: number;
  areaCm2: number | null;
  closed: boolean;
  loopCount: number;
}

export interface MeshSectionFailure {
  ok: false;
  reason: string;
}

export type MeshSectionResult = MeshSection | MeshSectionFailure;

/** Either section kind the review screen can show. */
export type SectionResult = MeshSectionResult | import("./crosssection").CrossSectionResult;

type V3 = [number, number, number];

interface Loop {
  points: V3[];
  closed: boolean;
}

/** Slice an indexed mesh with the plane through q with unit normal n. */
export function slicePlane(
  pos: ArrayLike<number>,
  idx: ArrayLike<number>,
  n: readonly [number, number, number],
  q: readonly [number, number, number],
): Loop[] {
  const nv = pos.length / 3;
  const d0 = n[0] * q[0] + n[1] * q[1] + n[2] * q[2];
  const s = new Float64Array(nv);
  for (let v = 0; v < nv; v++)
    s[v] = n[0] * pos[v * 3] + n[1] * pos[v * 3 + 1] + n[2] * pos[v * 3 + 2] - d0;

  const pts = new Map<number, V3>();
  const adj = new Map<number, number[]>();
  const keyOf = (a: number, b: number) => (a < b ? a * nv + b : b * nv + a);
  const pointOn = (a: number, b: number, key: number) => {
    if (pts.has(key)) return;
    const t = s[a] / (s[a] - s[b]);
    pts.set(key, [
      pos[a * 3] + t * (pos[b * 3] - pos[a * 3]),
      pos[a * 3 + 1] + t * (pos[b * 3 + 1] - pos[a * 3 + 1]),
      pos[a * 3 + 2] + t * (pos[b * 3 + 2] - pos[a * 3 + 2]),
    ]);
  };
  const link = (k1: number, k2: number) => {
    if (!adj.has(k1)) adj.set(k1, []);
    if (!adj.has(k2)) adj.set(k2, []);
    adj.get(k1)!.push(k2);
    adj.get(k2)!.push(k1);
  };

  for (let f = 0; f < idx.length; f += 3) {
    const t0 = idx[f], t1 = idx[f + 1], t2 = idx[f + 2];
    const u0 = s[t0] >= 0, u1 = s[t1] >= 0, u2 = s[t2] >= 0;
    if (u0 === u1 && u1 === u2) continue;
    const keys: number[] = [];
    if (u0 !== u1) { const k = keyOf(t0, t1); pointOn(t0, t1, k); keys.push(k); }
    if (u1 !== u2) { const k = keyOf(t1, t2); pointOn(t1, t2, k); keys.push(k); }
    if (u2 !== u0) { const k = keyOf(t2, t0); pointOn(t2, t0, k); keys.push(k); }
    if (keys.length === 2) link(keys[0], keys[1]);
  }

  const used = new Set<number>();
  const loops: Loop[] = [];
  const walk = (start: number): Loop => {
    const chain = [start];
    used.add(start);
    let prev: number | null = null;
    let cur = start;
    for (;;) {
      const next = (adj.get(cur) || []).find((k) => k !== prev && !used.has(k));
      if (next === undefined) break;
      chain.push(next);
      used.add(next);
      prev = cur;
      cur = next;
    }
    const closed = chain.length > 2 && (adj.get(cur) || []).includes(start);
    return { points: chain.map((k) => pts.get(k)!), closed };
  };
  for (const [k, nb] of adj) if (nb.length === 1 && !used.has(k)) loops.push(walk(k));
  for (const k of adj.keys()) if (!used.has(k)) loops.push(walk(k));
  return loops.filter((l) => l.points.length >= 2);
}

function polylineLength(p: number[][], closed: boolean): number {
  let L = 0;
  const n = p.length;
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const a = p[i], b = p[(i + 1) % n];
    let d = 0;
    for (let k = 0; k < a.length; k++) d += (b[k] - a[k]) ** 2;
    L += Math.sqrt(d);
  }
  return L;
}

function convexHull2D(p: [number, number][]): [number, number][] {
  const pts = p.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o: number[], a: number[], b: number[]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  const upper: [number, number][] = [];
  for (const q of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop();
    lower.push(q);
  }
  for (let i = pts.length - 1; i >= 0; i--) {
    const q = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop();
    upper.push(q);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function planeBasis(n: readonly number[]) {
  const a = Math.abs(n[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  let u = [n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2], n[0] * a[1] - n[1] * a[0]];
  const l = Math.hypot(u[0], u[1], u[2]);
  u = u.map((x) => x / l);
  const v = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]];
  return { u, v };
}

/** Circumference of the limb where the plane (q, n) crosses the surface. */
export function circumferenceOnPlane(
  pos: ArrayLike<number>,
  idx: ArrayLike<number>,
  q: readonly [number, number, number],
  nIn: readonly [number, number, number],
): MeshSectionResult {
  const l = Math.hypot(nIn[0], nIn[1], nIn[2]) || 1;
  const n: [number, number, number] = [nIn[0] / l, nIn[1] / l, nIn[2] / l];
  const loops = slicePlane(pos, idx, n, q);
  if (!loops.length) return { ok: false, reason: "the plane does not cross the limb" };
  const len = (lp: Loop) => polylineLength(lp.points, lp.closed);
  const closed = loops.filter((lp) => lp.closed);
  const pick = (closed.length ? closed : loops).reduce((a, b) => (len(b) > len(a) ? b : a));
  const { u, v } = planeBasis(n);
  const flat: [number, number][] = pick.points.map((p) => {
    const d = [p[0] - q[0], p[1] - q[1], p[2] - q[2]];
    return [d[0] * u[0] + d[1] * u[1] + d[2] * u[2], d[0] * v[0] + d[1] * v[1] + d[2] * v[2]];
  });
  let area: number | null = null;
  if (pick.closed) {
    let A = 0;
    for (let i = 0; i < flat.length; i++) {
      const a = flat[i], b = flat[(i + 1) % flat.length];
      A += a[0] * b[1] - b[0] * a[1];
    }
    area = Math.abs(A) / 2;
  }
  return {
    ok: true,
    kind: "mesh",
    tapeCm: polylineLength(convexHull2D(flat), true),
    contourCm: len(pick),
    areaCm2: area,
    closed: pick.closed,
    loopCount: loops.length,
  };
}
