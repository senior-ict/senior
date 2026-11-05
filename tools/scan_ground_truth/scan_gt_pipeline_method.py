"""Measure the scan's segment volume with the pipeline's own cut and volume code.

The point of this script is that nothing about the measurement differs between
the ground truth and the reconstruction. It loads the 3D scan, finds the same
two band planes the pipeline finds, pushes each plane out to the band's inner
edge, and then hands the mesh to the very functions stage 5 and stage 6 use:
trimesh's capped plane slice, and the exact volume of the resulting watertight
mesh. Any difference that survives is a difference in the limb, not in how the
two numbers were produced.

It also reports the limb's circumference at each inner edge, and the span
between them, so a volume difference can be attributed to girth or to length.
"""

import argparse
import gc
import os
import sys

import numpy as np
import open3d as open3d_library
import trimesh
from scipy.spatial import ConvexHull

# Both this folder and the repository root have to be importable: the scripts
# here import each other, and gt_vs_pipeline reuses the pipeline's own cutting
# code so the ground truth is cut exactly the way a reconstruction is.
_THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
_REPOSITORY_ROOT = os.path.dirname(os.path.dirname(_THIS_FOLDER))
for _folder in (_THIS_FOLDER, _REPOSITORY_ROOT):
    if _folder not in sys.path:
        sys.path.insert(0, _folder)

from scan_band_circumference import (excess_green, plane_of, band_edges,
                                     hull_perimeter, LEAST_GREENNESS,
                                     SMALLEST_BAND, SMALLEST_ARC,
                                     CLUSTER_REACH_MM)
from segment_cut import cut_between_planes


def find_band_rings(points, colours):
    """Split the scan's green points into the two band rings.

    This repeats what the circumference script does: keep strongly green
    points, drop stray specks with a density cluster, then split the survivors
    into two groups by where they sit along the line joining them.
    """
    green = excess_green(colours)
    on_band = green >= LEAST_GREENNESS
    band_points = points[on_band]

    cloud = open3d_library.geometry.PointCloud(
        open3d_library.utility.Vector3dVector(band_points))
    labels = np.array(cloud.cluster_dbscan(eps=CLUSTER_REACH_MM, min_points=10))
    solid = np.zeros(len(band_points), dtype=bool)
    for label in range(labels.max() + 1):
        chosen = labels == label
        if chosen.sum() >= SMALLEST_ARC:
            solid |= chosen
    band_points = band_points[solid]

    centred = band_points - band_points.mean(axis=0)
    _, _, directions = np.linalg.svd(centred, full_matrices=False)
    along = centred @ directions[0]
    split = 0.5 * (np.quantile(along, 0.02) + np.quantile(along, 0.98))
    rings = [band_points[along < split], band_points[along >= split]]
    return [ring for ring in rings if len(ring) >= SMALLEST_BAND]


def inner_edge_planes(rings):
    """Return one cutting plane per band, sitting on the band's inner edge.

    The plane's normal points from its own band toward the other one, so the
    segment to be measured lies on the positive side of both planes, and the
    cord itself lies outside the segment.
    """
    planes = []
    for ring in rings:
        centre, normal = plane_of(ring)
        other_ring = [entry for entry in rings if entry is not ring][0]
        toward_other = other_ring.mean(axis=0) - centre
        if normal @ toward_other < 0:
            normal = -normal
        low_edge, high_edge = band_edges(ring, centre, normal)
        planes.append({
            "centroid": centre + high_edge * normal,
            "normal": normal,
            "band_circumference_mm": hull_perimeter(ring, centre, normal),
            "cord_width_mm": high_edge - low_edge,
        })
    return planes


# Read the girth a few millimetres inside the cut face, never straddling it.
# The cord sits just outside the face, so a slab centred on the plane sweeps
# half a cord's thickness into the measurement and reads the limb too fat.
SLAB_INSET_MM = 2.5
SLAB_HALF_THICKNESS_MM = 1.5


def circumference_at(points, plane_origin, plane_normal, slab_half_mm,
                     reach_mm, inset_mm=SLAB_INSET_MM):
    """Convex hull perimeter of the limb in a thin slab inside a cutting plane.

    The hull is what a tape reads, because a tape bridges every concavity
    rather than dipping into it. The slab sits `inset_mm` inside the plane,
    on the segment's side, so no part of the cord is included.
    """
    offset = points - plane_origin
    along = offset @ plane_normal
    sideways = np.linalg.norm(offset - np.outer(along, plane_normal), axis=1)
    inside = (np.abs(along - inset_mm) < slab_half_mm) & (sideways < reach_mm)
    if inside.sum() < 30:
        return None, int(inside.sum())

    first_cross = np.cross(plane_normal, [1.0, 0.0, 0.0])
    if np.linalg.norm(first_cross) < 1e-6:
        first_cross = np.cross(plane_normal, [0.0, 1.0, 0.0])
    first_cross = first_cross / np.linalg.norm(first_cross)
    second_cross = np.cross(plane_normal, first_cross)

    local = points[inside] - plane_origin
    flat = np.stack([local @ first_cross, local @ second_cross], axis=1)
    hull = ConvexHull(flat)
    loop = flat[hull.vertices]
    closed_loop = np.vstack([loop, loop[:1]])
    perimeter = float(np.sum(np.linalg.norm(np.diff(closed_loop, axis=0), axis=1)))
    return perimeter, int(inside.sum())


def repair_scan_mesh(mesh):
    """Keep the largest connected piece and fill its holes.

    A handheld scan often closes with a few stray specks of floor beside the
    limb, and with small holes where the scanner saw nothing. Stage 5 does the
    same two things to a reconstruction before measuring it, so doing them here
    keeps the ground truth on the same footing rather than giving it an easier
    mesh than the pipeline gets.
    """
    pieces = mesh.split(only_watertight=False)
    if len(pieces) > 1:
        mesh = max(pieces, key=lambda piece: len(piece.faces))

    import pymeshfix

    # Called exactly as pipeline/workers/meshfix_worker.py calls it, including
    # leaving joincomp and remove_smallest_components off, so the reference is
    # repaired by the same recipe a reconstruction is.
    fixer = pymeshfix.MeshFix(
        np.ascontiguousarray(mesh.vertices, dtype=np.float64),
        np.ascontiguousarray(mesh.faces, dtype=np.int32))
    fixer.repair(joincomp=False, remove_smallest_components=False)
    repaired_vertices = np.asarray(fixer.points, dtype=np.float64)
    repaired_faces = np.asarray(fixer.faces, dtype=np.int64)
    return trimesh.Trimesh(vertices=repaired_vertices, faces=repaired_faces,
                           process=False)


def main():
    """Cut the scan at its band inner edges and measure it the pipeline's way."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--repair", action="store_true",
                        help="keep the largest connected piece and fill its "
                             "holes before cutting, which is what stage 5 does "
                             "to a reconstruction. Needed on a scan that the "
                             "scanner left open.")
    arguments = parser.parse_args()

    open3d_mesh = open3d_library.io.read_triangle_mesh(arguments.scan)
    points = np.asarray(open3d_mesh.vertices)
    colours = np.asarray(open3d_mesh.vertex_colors)
    faces = np.asarray(open3d_mesh.triangles)
    del open3d_mesh
    gc.collect()

    rings = find_band_rings(points, colours)
    if len(rings) != 2:
        print(f"{arguments.label}: found {len(rings)} bands, expected 2")
        return

    # Name the bands by ring size, so the thinner one is always the ankle.
    ring_size = [float(np.median(np.linalg.norm(ring - ring.mean(axis=0), axis=1)))
                 for ring in rings]
    if ring_size[0] > ring_size[1]:
        rings = rings[::-1]

    planes = inner_edge_planes(rings)
    limb_axis = planes[1]["centroid"] - planes[0]["centroid"]
    span_mm = float(np.linalg.norm(limb_axis))
    limb_axis = limb_axis / span_mm

    scan_mesh = trimesh.Trimesh(vertices=points, faces=faces, process=False)
    if arguments.repair:
        scan_mesh = repair_scan_mesh(scan_mesh)
        print(f"   repaired: {len(scan_mesh.vertices)} vertices, "
              f"watertight={scan_mesh.is_watertight}")
    markers = [{"centroid": plane["centroid"], "normal": plane["normal"]}
               for plane in planes]
    cut_mesh, case = cut_between_planes(scan_mesh, markers)

    print(f"\n{arguments.label}   scan measured with the pipeline's own cut and volume")
    print(f"   cut case: {case}")
    print(f"   inner edge to inner edge span: {span_mm / 10.0:.2f} cm")

    reach_mm = 0.9 * max(plane["band_circumference_mm"] for plane in planes) / np.pi
    for name, plane in zip(("ankle band", "knee band"), planes):
        circumference, used = circumference_at(points, plane["centroid"],
                                               plane["normal"],
                                               SLAB_HALF_THICKNESS_MM, reach_mm)
        shown = f"{circumference / 10.0:.2f} cm" if circumference else "not measurable"
        print(f"   {name:11} cord width {plane['cord_width_mm']:4.1f} mm"
              f"   limb at inner edge {shown}   ({used} pts)")

    print(f"   cut mesh: {len(cut_mesh.vertices)} vertices, "
          f"{len(cut_mesh.faces)} faces, watertight={cut_mesh.is_watertight}")
    if cut_mesh.is_watertight:
        volume_cm3 = abs(float(cut_mesh.volume)) / 1000.0
        print(f"   GROUND TRUTH VOLUME (watertight, pipeline method): "
              f"{volume_cm3:.1f} cm3")
    else:
        print("   not watertight after the cut, so the pipeline's exact volume")
        print("   method does not apply. The scan has holes that need filling")
        print("   first, the same way stage 5 repairs a reconstruction.")
        components = cut_mesh.split(only_watertight=False)
        print(f"   {len(components)} connected pieces; "
              f"largest has {len(max(components, key=lambda piece: len(piece.faces)).faces)} faces")


if __name__ == "__main__":
    main()
