"""Stage 5 — Cut the reconstructed limb with the confirmed planes (leg-scan-measure).

Input is Stage 4's surface (`04_recon/mesh/leg_recon.ply`), which is NOT yet
watertight: closing it is Stage 6's job, after the cut. The cut is
leg-scan-measure's exact plane cut (core/legscan.plane_cut): every triangle
crossing a plane is split along it, so each cut leaves one clean open boundary
loop that pymeshfix then caps flat in Stage 6.

Plane rule, unchanged from senior:
    None      -> cut deferred: publish the uncut limb only, measure nothing
    []        -> nothing to cut: the whole limb is the measurement
    1 plane   -> keep what is BELOW it
    2 planes  -> keep what lies BETWEEN them

Outputs (05_cut/mesh/):
    leg_no_cut.ply     the uncut limb, published for the review screen
    leg_cut_open.ply   the cut piece, open at the cut(s); absent when deferred
    ../cut_planes.json the planes actually applied (upward normals)
"""
import json
import os

import numpy as np
import trimesh

from pipeline.core.legscan import (connected_components, compact, edge_stats,
                                   slab_cut, upward_plane)

UNCUT_LIMB_NAME = "leg_no_cut.ply"
OPEN_CUT_NAME = "leg_cut_open.ply"
MAX_PLANES = 2
MIN_FACES_AFTER_CUT = 50


def _load(path):
    """Loads a PLY as (vertices, faces, colours or None) with duplicate vertices merged."""
    m = trimesh.load(path, force="mesh", process=False)
    m.merge_vertices()
    colors = None
    if m.visual.kind == "vertex":
        colors = np.asarray(m.visual.vertex_colors, dtype=np.float64)
    return np.asarray(m.vertices, dtype=np.float64), np.asarray(m.faces, dtype=np.int64), colors


def _save(path, v, f, c=None):
    """Writes a PLY, keeping vertex colours when present."""
    m = trimesh.Trimesh(vertices=v, faces=f, process=False)
    if c is not None:
        m.visual.vertex_colors = np.clip(np.rint(c), 0, 255).astype(np.uint8)
    m.export(path)


def _keep_main_piece(v, f, c):
    """Keeps the largest connected piece; a slab can catch stray bits of other geometry."""
    labels, count = connected_components(f, len(v))
    if count < 2:
        return v, f, c, 1
    biggest = np.bincount(labels).argmax()
    v2, f2, c2 = compact(v, f[labels == biggest], c)
    return v2, f2, c2, count


def cut_stage(limb_path, output_dir, cut_planes=None, height_axis="z"):
    """Runs Stage 5. Returns the path of leg_cut_open.ply, or None when deferred."""
    print()
    print("=" * 60)
    print("STAGE 5: Cut the limb (leg-scan-measure exact plane cut)")
    print("=" * 60)

    mesh_dir = os.path.join(output_dir, "mesh")
    os.makedirs(mesh_dir, exist_ok=True)
    for name in (UNCUT_LIMB_NAME, OPEN_CUT_NAME):
        p = os.path.join(mesh_dir, name)
        if os.path.exists(p):
            os.remove(p)
    planes_out = os.path.join(output_dir, "cut_planes.json")
    if os.path.exists(planes_out):
        os.remove(planes_out)

    v, f, c = _load(limb_path)
    print(f"  Limb surface: {limb_path}  ({len(v):,} v, {len(f):,} f, "
          f"open edges {edge_stats(f)['boundary_edges']:,})")
    _save(os.path.join(mesh_dir, UNCUT_LIMB_NAME), v, f, c)

    if cut_planes is None:
        print("  Cut deferred (--no-cut): published leg_no_cut.ply for review only")
        return None

    up = np.zeros(3)
    up[{"x": 0, "y": 1, "z": 2}[height_axis]] = 1.0
    planes = []
    for marker in list(cut_planes)[:MAX_PLANES]:
        pl = upward_plane(marker, up)
        if pl is None:
            print("  Skipping a vertical plane (no above/below)")
            continue
        planes.append(pl)

    cv, cf, cc, case = slab_cut(v, f, planes, up, c)
    if len(cf) < MIN_FACES_AFTER_CUT:
        print(f"  Cut left {len(cf)} faces — planes miss the limb; measuring the whole limb")
        cv, cf, cc, case, planes = v, f, c, "too_few_after_cut", []
    cv, cf, cc, pieces = _keep_main_piece(cv, cf, cc)
    if pieces > 1:
        print(f"  Cut left {pieces} pieces — kept the largest")

    out = os.path.join(mesh_dir, OPEN_CUT_NAME)
    _save(out, cv, cf, cc)
    with open(planes_out, "w") as fh:
        json.dump({"case": case, "space": "levelled", "height_axis": height_axis,
                   "planes": [{"centroid": q.tolist(), "normal": n.tolist()}
                              for q, n in planes]}, fh, indent=2)
    print(f"  Cut ({case}, {len(planes)} plane(s)): {len(cv):,} v, {len(cf):,} f, "
          f"open edges {edge_stats(cf)['boundary_edges']:,}")
    print(f"  -> {out}")
    return out
