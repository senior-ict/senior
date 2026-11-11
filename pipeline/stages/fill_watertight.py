"""Stage 6 — Fill to watertight with pymeshfix (leg-scan-measure /api/repair).

Closes the cut piece's open ends (and any holes Poisson's density trim left)
into a single watertight solid, and does the same for the reference cube so
Stage 7 can scale against an exact volume.

pymeshfix options follow leg-scan-measure's defaults: keep only the main piece
(removes noise), do not join nearby pieces. Vertex colours are carried over
from the input by nearest neighbour, since pymeshfix drops them.

Outputs (06_fill/mesh/):
    leg_cut.ply        watertight limb segment (absent when the cut is deferred)
    box.ply            watertight reference cube
    scene_colour.ply   both merged, for the result screen
    ../repair.json     before/after edge stats per mesh
"""
import json
import os

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from pipeline.core.legscan import meshfix_repair

CUT_LIMB_NAME = "leg_cut.ply"
BOX_NAME = "box.ply"


def _repair_file(src, dst, joincomp=False, remove_small=True):
    """Repairs one mesh file into dst. Returns pymeshfix's info dict."""
    m = trimesh.load(src, force="mesh", process=False)
    m.merge_vertices()
    rv, rf, info = meshfix_repair(m.vertices, m.faces, joincomp=joincomp,
                                  remove_small=remove_small)
    out = trimesh.Trimesh(vertices=rv, faces=rf, process=False)
    if m.visual.kind == "vertex" and len(m.vertices):
        _, idx = cKDTree(np.asarray(m.vertices)).query(rv)
        out.visual.vertex_colors = np.asarray(m.visual.vertex_colors)[idx]
    out.export(dst)
    out.export(os.path.splitext(dst)[0] + ".stl")
    info["source"] = os.path.relpath(src)
    flag = "watertight" if info["watertight"] else "NOT watertight"
    print(f"  {os.path.basename(dst):<14} open edges {info['before']['boundary_edges']:,} -> "
          f"{info['after']['boundary_edges']:,}, non-manifold "
          f"{info['after']['nonmanifold_edges']}, {info['faces']:,} f  [{flag}, {info['method']}]")
    return info


def fill_stage(open_cut_path, box_path, output_dir, joincomp=False, remove_small=True):
    """Runs Stage 6. Returns {name: path} of the watertight meshes written."""
    print()
    print("=" * 60)
    print("STAGE 6: Fill to watertight (pymeshfix)")
    print("=" * 60)

    mesh_dir = os.path.join(output_dir, "mesh")
    os.makedirs(mesh_dir, exist_ok=True)
    for name in os.listdir(mesh_dir):
        os.remove(os.path.join(mesh_dir, name))

    written, report = {}, {}
    if box_path and os.path.exists(box_path):
        dst = os.path.join(mesh_dir, BOX_NAME)
        report["box"] = _repair_file(box_path, dst, joincomp, remove_small)
        written["box"] = dst
    else:
        print("  No reference cube mesh — Stage 7 will not be able to scale")

    if open_cut_path and os.path.exists(open_cut_path):
        dst = os.path.join(mesh_dir, CUT_LIMB_NAME)
        report["leg_cut"] = _repair_file(open_cut_path, dst, joincomp, remove_small)
        written["leg_cut"] = dst
    else:
        print("  No cut limb (cut deferred) — only the reference is repaired")

    if written:
        parts = [trimesh.load(p, process=False) for p in written.values()]
        scene = trimesh.util.concatenate(parts)
        scene_path = os.path.join(mesh_dir, "scene_colour.ply")
        scene.export(scene_path)
        written["scene_colour"] = scene_path

    with open(os.path.join(output_dir, "repair.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    return written
