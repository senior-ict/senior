"""Compare the pipeline's cut segment against the scan's, measured identically.

Both sides are cut at the band inner edges with the pipeline's own plane slice,
both volumes are the exact volume of the resulting watertight mesh, and both
circumferences are read from a slab placed the same small distance inside the
cut face, so no cord is caught on either side. The output separates the volume
difference into the part explained by length and the part explained by girth.
"""

import argparse
import gc
import json
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

from scan_gt_pipeline_method import find_band_rings, inner_edge_planes
from segment_cut import cut_between_planes

# Read the girth a few millimetres inside the cut face, never across it. On the
# scan side the cord sits just outside the face and would be swept in; on the
# pipeline side the face is a flat cap whose vertices carry no wall.
SLAB_INSET_MM = 2.5
SLAB_HALF_THICKNESS_MM = 1.5


def hull_perimeter_of_slab(points, plane_origin, plane_normal,
                           inset_mm, half_thickness_mm, reach_mm):
    """Convex hull perimeter of a thin slab taken a set distance inside a plane."""
    offset = points - plane_origin
    along = offset @ plane_normal
    sideways = np.linalg.norm(offset - np.outer(along, plane_normal), axis=1)
    inside = (np.abs(along - inset_mm) < half_thickness_mm) & (sideways < reach_mm)
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


def measure_scan(scan_path):
    """Cut the scan at its band inner edges and measure it the pipeline's way."""
    open3d_mesh = open3d_library.io.read_triangle_mesh(scan_path)
    points = np.asarray(open3d_mesh.vertices)
    colours = np.asarray(open3d_mesh.vertex_colors)
    faces = np.asarray(open3d_mesh.triangles)
    del open3d_mesh
    gc.collect()

    rings = find_band_rings(points, colours)
    ring_size = [float(np.median(np.linalg.norm(ring - ring.mean(axis=0), axis=1)))
                 for ring in rings]
    if ring_size[0] > ring_size[1]:
        rings = rings[::-1]

    planes = inner_edge_planes(rings)
    axis_vector = planes[1]["centroid"] - planes[0]["centroid"]
    span_mm = float(np.linalg.norm(axis_vector))
    limb_axis = axis_vector / span_mm
    scan_tilts = [float(np.degrees(np.arccos(abs(plane["normal"] @ limb_axis))))
                  for plane in planes]

    scan_mesh = trimesh.Trimesh(vertices=points, faces=faces, process=False)
    markers = [{"centroid": plane["centroid"], "normal": plane["normal"]}
               for plane in planes]
    cut_mesh, _case = cut_between_planes(scan_mesh, markers)

    reach_mm = 0.9 * max(plane["band_circumference_mm"] for plane in planes) / np.pi
    girths = []
    for plane in planes:
        perimeter, _used = hull_perimeter_of_slab(
            points, plane["centroid"], plane["normal"],
            SLAB_INSET_MM, SLAB_HALF_THICKNESS_MM, reach_mm)
        girths.append(perimeter)

    return {
        "span_cm": span_mm / 10.0,
        "ankle_girth_cm": girths[0] / 10.0,
        "knee_girth_cm": girths[1] / 10.0,
        "volume_cm3": abs(float(cut_mesh.volume)) / 1000.0,
        "watertight": bool(cut_mesh.is_watertight),
        "plane_tilts_deg": scan_tilts,
    }


def measure_pipeline(run_folder, centimetres_per_unit):
    """Measure the pipeline's cut segment on the same two planes it was cut by.

    The cut planes are stored in levelled space by stage 3 and the cut mesh is
    written in that same space, so the girth can be read on each plane exactly
    as it is read on the scan. Taking the mesh's own extent instead would be
    wrong: the band planes are tilted by about twenty degrees, so the furthest
    vertex along any straight axis is a corner of the cut face, not the face.
    """
    cut_mesh = trimesh.load(f"{run_folder}/05_watertight/mesh/leg_cut.ply",
                            process=False)
    points = np.asarray(cut_mesh.vertices) * centimetres_per_unit * 10.0

    with open(f"{run_folder}/03_clean/debug/cutting_line_levelled.json") as handle:
        markers = json.load(handle)["markers"]
    origins = [np.asarray(marker["centroid"]) * centimetres_per_unit * 10.0
               for marker in markers]
    normals = [np.asarray(marker["normal"], dtype=np.float64) for marker in markers]
    normals = [normal / np.linalg.norm(normal) for normal in normals]

    # Point each plane's normal at the other plane, so the segment lies on the
    # positive side of both, matching how the scan's planes are oriented.
    for index in (0, 1):
        toward_other = origins[1 - index] - origins[index]
        if normals[index] @ toward_other < 0:
            normals[index] = -normals[index]

    span_mm = float(np.linalg.norm(origins[1] - origins[0]))
    limb_axis = (origins[1] - origins[0]) / span_mm
    along = (points - origins[0]) @ limb_axis
    reach_mm = 3.0 * float(np.median(np.linalg.norm(
        (points - origins[0]) - np.outer(along, limb_axis), axis=1)))

    girths = []
    for origin, normal in zip(origins, normals):
        perimeter, _used = hull_perimeter_of_slab(
            points, origin, normal, SLAB_INSET_MM,
            SLAB_HALF_THICKNESS_MM, reach_mm)
        girths.append(perimeter)
    if girths[0] is None or girths[1] is None:
        raise RuntimeError("a cut plane caught too few vertices to measure")
    if girths[0] > girths[1]:
        girths = girths[::-1]

    tilts = [float(np.degrees(np.arccos(abs(normal @ limb_axis))))
             for normal in normals]

    volume_cm3 = abs(float(cut_mesh.volume)) * centimetres_per_unit ** 3
    return {
        "span_cm": span_mm / 10.0,
        "ankle_girth_cm": girths[0] / 10.0,
        "knee_girth_cm": girths[1] / 10.0,
        "volume_cm3": volume_cm3,
        "watertight": bool(cut_mesh.is_watertight),
        "plane_tilts_deg": tilts,
    }


def cone_volume(span_cm, ankle_girth_cm, knee_girth_cm):
    """Volume of a truncated cone with the given length and two circumferences.

    Used only to ask how much of the measured volume difference the two end
    girths and the length already account for.
    """
    return (span_cm / (12.0 * np.pi)) * (ankle_girth_cm ** 2
                                         + ankle_girth_cm * knee_girth_cm
                                         + knee_girth_cm ** 2)


def main():
    """Print the scan and pipeline side by side with the error attributed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--cm-per-unit", type=float, required=True)
    parser.add_argument("--label", default="")
    arguments = parser.parse_args()

    scan = measure_scan(arguments.scan)
    pipeline = measure_pipeline(arguments.run, arguments.cm_per_unit)

    print(f"\n{arguments.label}")
    print("                        scan      pipeline     error")
    for name, key, unit in (("span (length)", "span_cm", "cm"),
                            ("ankle girth", "ankle_girth_cm", "cm"),
                            ("knee girth", "knee_girth_cm", "cm"),
                            ("VOLUME", "volume_cm3", "cm3")):
        error = 100.0 * (pipeline[key] / scan[key] - 1.0)
        print(f"   {name:18} {scan[key]:9.2f} {pipeline[key]:11.2f}"
              f"   {error:+7.2f}% {unit}")
    print(f"   watertight         {str(scan['watertight']):>9} "
          f"{str(pipeline['watertight']):>11}")
    print(f"   cut plane tilt off the limb axis: scan "
          f"{scan['plane_tilts_deg'][0]:.1f} and {scan['plane_tilts_deg'][1]:.1f} deg,"
          f"  pipeline {pipeline['plane_tilts_deg'][0]:.1f} and "
          f"{pipeline['plane_tilts_deg'][1]:.1f} deg")

    scan_cone = cone_volume(scan["span_cm"], scan["ankle_girth_cm"],
                            scan["knee_girth_cm"])
    pipeline_cone = cone_volume(pipeline["span_cm"], pipeline["ankle_girth_cm"],
                                pipeline["knee_girth_cm"])
    print(f"\n   how much the length and the two end girths already explain:")
    print(f"     a cone on those numbers alone would differ by "
          f"{100.0 * (pipeline_cone / scan_cone - 1.0):+.2f}%")

    length_only = 100.0 * (pipeline["span_cm"] / scan["span_cm"] - 1.0)
    girth_only = 100.0 * (cone_volume(scan["span_cm"],
                                      pipeline["ankle_girth_cm"],
                                      pipeline["knee_girth_cm"]) / scan_cone - 1.0)
    print(f"     of which length contributes {length_only:+.2f}% "
          f"and girth {girth_only:+.2f}%")


if __name__ == "__main__":
    main()
