"""Mesh operations ported from leg-scan-measure (static/meshops.js, server.py).

Stages 5-7 of this pipeline are leg-scan-measure's method applied to the mesh
senior's Stage 4 reconstructs:

    Stage 5  cut      exact plane cut: triangles crossing a plane are split and
                      the new vertices de-duplicated per edge, so each cut
                      leaves one clean boundary loop (planeCut / slabCut)
    Stage 6  fill     pymeshfix closes the open cut ends (and any holes the
                      Poisson trim left) into a watertight solid
    Stage 7  measure  signed tetrahedron volume V = sum a.(b x c) / 6 in
                      float64, and circumference where each cutting plane meets
                      the surface: tape = convex hull perimeter in the plane,
                      contour = exact outline length (circumferenceOnPlane)

All functions take and return plain numpy arrays: vertices (n, 3) float64 and
faces (m, 3) int64, plus optional per-vertex colours (n, k).
"""
from __future__ import annotations

import numpy as np

# ── basic helpers ─────────────────────────────────────────────────────────


def compact(vertices, faces, colors=None):
    """Drop degenerate faces (a repeated index) and unreferenced vertices."""
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    ok = ((faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
          & (faces[:, 0] != faces[:, 2]))
    faces = faces[ok]
    used = np.unique(faces)
    remap = np.full(len(vertices), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out_c = None if colors is None else np.asarray(colors)[used]
    return np.asarray(vertices)[used], remap[faces], out_c


def edge_stats(faces):
    """Count boundary (used once) and non-manifold (used >2) edges."""
    faces = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(faces) == 0:
        return {"boundary_edges": 0, "nonmanifold_edges": 0}
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return {"boundary_edges": int((counts == 1).sum()),
            "nonmanifold_edges": int((counts > 2).sum())}


def is_closed(faces):
    """True when every edge is shared by exactly two faces."""
    s = edge_stats(faces)
    return s["boundary_edges"] == 0 and s["nonmanifold_edges"] == 0


def signed_volume(vertices, faces):
    """Signed tetrahedron volume  V = sum a.(b x c) / 6, float64.

    Reference point is the bbox centre rather than the origin, for precision
    (same as leg-scan-measure). Requires a closed, consistently oriented mesh.
    """
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    if len(f) == 0:
        return 0.0
    c = (v.min(axis=0) + v.max(axis=0)) / 2.0
    a, b, d = v[f[:, 0]] - c, v[f[:, 1]] - c, v[f[:, 2]] - c
    return float(np.einsum("ij,ij->i", a, np.cross(b, d)).sum() / 6.0)


def surface_area(vertices, faces):
    """Total triangle area."""
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    cr = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    return float(np.linalg.norm(cr, axis=1).sum() / 2.0)


# ── Stage 5: exact plane cut ──────────────────────────────────────────────


def plane_cut(vertices, faces, normal, d, colors=None):
    """Cut with plane n.p + d = 0, keeping the side where n.p + d >= 0.

    Port of meshops.planeCut. Triangles crossing the plane are split; the new
    vertex on each crossed edge is created once and shared by both neighbouring
    triangles, so the cut leaves a single clean boundary loop. Winding is
    preserved.
    """
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    col = None if colors is None else np.asarray(colors, dtype=np.float64)
    n = len(v)
    s = v @ np.asarray(normal, dtype=np.float64) + float(d)
    inside = s >= 0
    cnt = inside[f].sum(axis=1)

    keep_whole = f[cnt == 3]
    crossing = f[(cnt == 1) | (cnt == 2)]

    new_pos, new_col = [], []
    cache = {}

    def isect(a, b):
        # a inside, b outside
        key = (a, b) if a < b else (b, a)
        r = cache.get(key)
        if r is not None:
            return r
        t = s[a] / (s[a] - s[b])
        if t <= 1e-9:
            r = a
        else:
            new_pos.append(v[a] + t * (v[b] - v[a]))
            if col is not None:
                new_col.append(col[a] + t * (col[b] - col[a]))
            r = n + len(new_pos) - 1
        cache[key] = r
        return r

    out = []
    for tri in crossing.tolist():
        ins = [bool(inside[x]) for x in tri]
        if sum(ins) == 1:
            r = ins.index(True)
            a, b, c = tri[r], tri[(r + 1) % 3], tri[(r + 2) % 3]
            out.append((a, isect(a, b), isect(a, c)))
        else:
            r = ins.index(False)
            c, a, b = tri[r], tri[(r + 1) % 3], tri[(r + 2) % 3]
            bc, ac = isect(b, c), isect(a, c)
            out.append((a, b, bc))
            out.append((a, bc, ac))

    all_v = np.vstack([v, np.asarray(new_pos).reshape(-1, 3)]) if new_pos else v
    all_c = None
    if col is not None:
        all_c = np.vstack([col, np.asarray(new_col).reshape(-1, col.shape[1])]) if new_col else col
    all_f = np.vstack([keep_whole, np.asarray(out, dtype=np.int64).reshape(-1, 3)])
    return compact(all_v, all_f, all_c)


def upward_plane(marker, up_axis):
    """(point, unit normal pointing along up_axis), or None for a vertical plane."""
    q = np.asarray(marker["centroid"], dtype=np.float64)
    nrm = np.asarray(marker["normal"], dtype=np.float64)
    nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
    up = float(nrm @ up_axis)
    if abs(up) < 1e-3:
        return None
    return q, (nrm if up > 0 else -nrm)


def slab_cut(vertices, faces, planes, up_axis, colors=None):
    """Apply 1 or 2 cutting planes the way senior defines them.

    1 plane  -> keep what is BELOW it
    2 planes -> keep what lies BETWEEN them (leg-scan-measure slabCut:
                keep nb.(p-qb) >= 0 and nt.(p-qt) <= 0)

    `planes` are (point, upward unit normal) pairs. Returns (v, f, c, case).
    """
    up_axis = np.asarray(up_axis, dtype=np.float64)
    if not planes:
        return vertices, faces, colors, "no_planes"
    if len(planes) == 1:
        q, nt = planes[0]
        v, f, c = plane_cut(vertices, faces, -nt, float(nt @ q), colors)
        return v, f, c, "below_one_plane"
    (q1, n1), (q2, n2) = planes[:2]
    if float(q1 @ up_axis) > float(q2 @ up_axis):
        (q1, n1), (q2, n2) = (q2, n2), (q1, n1)
    v, f, c = plane_cut(vertices, faces, n1, -float(n1 @ q1), colors)
    v, f, c = plane_cut(v, f, -n2, float(n2 @ q2), c)
    return v, f, c, "between_two_planes"


def connected_components(faces, n_vertices):
    """Label faces by vertex-connected component. Returns (labels, count)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components as cc
    f = np.asarray(faces, dtype=np.int64)
    if len(f) == 0:
        return np.zeros(0, dtype=np.int64), 0
    rows = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    cols = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    g = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_vertices, n_vertices))
    _, vlab = cc(g, directed=False)
    flab = vlab[f[:, 0]]
    uniq, flab = np.unique(flab, return_inverse=True)
    return flab, len(uniq)


# ── Stage 6: pymeshfix fill ───────────────────────────────────────────────


def meshfix_repair(vertices, faces, joincomp=False, remove_small=True):
    """Close holes into a watertight solid with pymeshfix (leg-scan-measure /api/repair).

    `remove_small` keeps only the main piece (leg-scan-measure's default:
    "Keep only the main piece (removes noise)"). Faces are flipped if the
    result is inside out, so the signed volume comes out positive.
    """
    import pymeshfix

    v_in = np.ascontiguousarray(vertices, dtype=np.float64)
    f_in = np.ascontiguousarray(faces, dtype=np.int32)
    before = edge_stats(f_in)

    # Full repair: fills holes AND removes self-intersections / non-manifold
    # edges (what leg-scan-measure's /api/repair runs).
    mf = pymeshfix.MeshFix(v_in, f_in)
    mf.repair(joincomp=bool(joincomp), remove_smallest_components=bool(remove_small))
    rv = np.asarray(mf.points, dtype=np.float64)
    rf = np.asarray(mf.faces, dtype=np.int64).reshape(-1, 3)
    method = "repair"

    # Guard: repair() can discard most of a clean but very regular surface
    # (measured: a sliced 256-segment cylinder kept a 5% wedge). Filling the
    # holes alone only ever ADDS faces, so when repair() returns markedly fewer
    # faces than hole-filling does, its output is a loss, not a repair.
    hf = pymeshfix.MeshFix(v_in, f_in)
    if remove_small:
        hf.remove_smallest_components()
    hf.fill_holes()
    hv = np.asarray(hf.points, dtype=np.float64)
    hfaces = np.asarray(hf.faces, dtype=np.int64).reshape(-1, 3)
    if len(hfaces) and (len(rf) < 0.9 * len(hfaces) or not is_closed(rf)) and is_closed(hfaces):
        rv, rf, method = hv, hfaces, "fill_holes (repair discarded geometry)"
    if len(rf) == 0:
        raise RuntimeError("pymeshfix returned an empty mesh")
    vol = signed_volume(rv, rf)
    if vol < 0:
        rf = rf[:, [0, 2, 1]]
        vol = -vol
    after = edge_stats(rf)
    info = {
        "volume": vol,
        "vertices": int(len(rv)),
        "faces": int(len(rf)),
        "watertight": after["boundary_edges"] == 0 and after["nonmanifold_edges"] == 0,
        "method": method,
        "before": before,
        "after": after,
    }
    return rv, rf, info


# ── Stage 7: circumference on a plane ─────────────────────────────────────


def slice_plane(vertices, faces, normal, point):
    """Slice the mesh with a plane. Returns loops [{"points": (k,3), "closed": bool}].

    Port of meshops.slicePlane: intersection points are keyed by mesh edge, so
    neighbouring triangles share them and the segments chain into exact loops.
    """
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    nrm = np.asarray(normal, dtype=np.float64)
    s = (v - np.asarray(point, dtype=np.float64)) @ nrm
    up = s >= 0
    mixed = f[(up[f].sum(axis=1) % 3) != 0]
    pts, adj = {}, {}

    def key_point(a, b):
        k = (a, b) if a < b else (b, a)
        if k not in pts:
            t = s[a] / (s[a] - s[b])
            pts[k] = v[a] + t * (v[b] - v[a])
        return k

    for tri in mixed.tolist():
        keys = []
        for e in range(3):
            a, b = tri[e], tri[(e + 1) % 3]
            if up[a] != up[b]:
                keys.append(key_point(a, b))
        if len(keys) == 2:
            k1, k2 = keys
            adj.setdefault(k1, []).append(k2)
            adj.setdefault(k2, []).append(k1)

    used, loops = set(), []

    def walk(start):
        chain = [start]
        used.add(start)
        prev, cur = None, start
        while True:
            nxt = next((k for k in adj.get(cur, []) if k != prev and k not in used), None)
            if nxt is None:
                break
            chain.append(nxt)
            used.add(nxt)
            prev, cur = cur, nxt
        closed = len(chain) > 2 and start in adj.get(cur, [])
        return {"points": np.array([pts[k] for k in chain]), "closed": closed}

    for k, nb in adj.items():
        if len(nb) == 1 and k not in used:
            loops.append(walk(k))
    for k in adj:
        if k not in used:
            loops.append(walk(k))
    return [lp for lp in loops if len(lp["points"]) >= 2]


def polyline_length(points, closed):
    p = np.asarray(points, dtype=np.float64)
    if len(p) < 2:
        return 0.0
    seg = np.diff(np.vstack([p, p[:1]]) if closed else p, axis=0)
    return float(np.linalg.norm(seg, axis=1).sum())


def convex_hull_2d(p):
    """Monotone-chain convex hull of (k, 2) points. Returns hull points (CCW)."""
    pts = sorted(map(tuple, np.asarray(p, dtype=np.float64)))
    if len(pts) < 3:
        return np.asarray(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.asarray(lower[:-1] + upper[:-1])


def plane_basis(n):
    """Orthonormal in-plane basis (u, v) for unit normal n."""
    n = np.asarray(n, dtype=np.float64)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    return u, np.cross(n, u)


def circumference_on_plane(vertices, faces, normal, point):
    """Circumference where a (possibly tilted) plane meets the mesh.

    Port of meshops.circumferenceOnPlane. Picks the longest closed loop (the
    leg; noise blobs and open bits lose), else the longest loop.
      tape    convex hull perimeter in the plane (measuring-tape length)
      contour exact outline length
      area    cross-section area (closed loops only)
    Returns None when the plane misses the mesh.
    """
    normal = np.asarray(normal, dtype=np.float64)
    normal = normal / (np.linalg.norm(normal) + 1e-12)
    point = np.asarray(point, dtype=np.float64)
    loops = slice_plane(vertices, faces, normal, point)
    if not loops:
        return None
    closed = [lp for lp in loops if lp["closed"]]
    pick = max(closed or loops, key=lambda lp: polyline_length(lp["points"], lp["closed"]))
    u, w = plane_basis(normal)
    rel = pick["points"] - point
    flat = np.stack([rel @ u, rel @ w], axis=1)
    hull = convex_hull_2d(flat)
    area = float("nan")
    if pick["closed"]:
        x, y = flat[:, 0], flat[:, 1]
        area = float(abs(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2.0)
    hull3 = point + hull[:, :1] * u + hull[:, 1:2] * w
    return {
        "tape": polyline_length(hull, True),
        "contour": polyline_length(pick["points"], pick["closed"]),
        "area": area,
        "closed": bool(pick["closed"]),
        "loop_count": len(loops),
        "hull": hull3,
    }
