"""One panel per horizontal slice: the cleaned points, the fitted ellipse, and
the cross-section of the watertight mesh at that same height.

If the mesh outline hugs the points, the wrap is faithful. Where it bulges past
them, the alpha shape has bridged to something -- a stray cluster, a ghost
sheet -- and that bulge is volume the limb never had. The per-slice area ratio
(mesh section / points' ellipse) says how much.

    python ring_gallery.py output_test6 [step_cm]
"""
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
import trimesh

import pathlib

# This file lives at docs/experiments/test_captures/, three levels below the
# repository root, and imports the pipeline from there.
PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parents[3])
sys.path.insert(0, PROJECT_ROOT)
from pipeline.core.crosssection import (ellipse_geometry, fit_ellipse_direct,
                                        plane_basis, ramanujan2)


def load_run(run_name):
    """Cleaned cloud, watertight solid, cm-per-unit scale, and the two planes."""
    debug = f"{PROJECT_ROOT}/{run_name}/for_debug"
    cloud = np.asarray(o3d.io.read_point_cloud(
        f"{debug}/03_clean/objects/leg.ply").points)
    solid = trimesh.load(f"{debug}/05_watertight/mesh/leg_no_cut.ply", process=False)
    box = trimesh.load(f"{debug}/05_watertight/mesh/box.ply", process=False)
    scale = (1000.0 / box.volume) ** (1.0 / 3.0)
    planes = sorted(json.load(open(
        f"{debug}/03_clean/debug/cutting_line_levelled.json"))["markers"],
        key=lambda plane: plane["centroid"][2])
    return cloud, solid, scale, planes


def slice_points(cloud, height, scale, half_mm=4.0):
    """Points within a thin horizontal slab, as centred 2-D cm coordinates."""
    basis_u, basis_v, basis_n = plane_basis(np.array([0.0, 0.0, 1.0]))
    centroid = np.array([0.0, 0.0, height])
    slab = cloud[np.abs((cloud - centroid) @ basis_n) <= (half_mm / 10.0) / scale]
    local = slab - centroid
    in_plane = np.stack([local @ basis_u, local @ basis_v], axis=1) * scale
    return in_plane


def mesh_section(solid, height, scale, centre_cm):
    """The solid's outline at this height, as a list of closed 2-D cm loops.

    The loop is projected through the same in-plane basis `slice_points` uses,
    so the two land in one frame whatever orientation plane_basis chooses.
    """
    section = solid.section(plane_origin=[0, 0, height], plane_normal=[0, 0, 1])
    if section is None:
        return []
    basis_u, basis_v, _ = plane_basis(np.array([0.0, 0.0, 1.0]))
    centroid = np.array([0.0, 0.0, height])
    loops = []
    for entity_points in section.discrete:
        local = np.asarray(entity_points) - centroid
        loop = np.stack([local @ basis_u, local @ basis_v], axis=1) * scale - centre_cm
        loops.append(loop)
    return loops


def polygon_area(loop):
    """Shoelace area of a closed loop."""
    x_coords, y_coords = loop[:, 0], loop[:, 1]
    return 0.5 * abs(np.dot(x_coords, np.roll(y_coords, 1))
                     - np.dot(y_coords, np.roll(x_coords, 1)))


def fit_ring(in_plane):
    """Ellipse fit of one slice; returns (centre, a, b, angle, girth) in cm."""
    centre, axis_a, axis_b, angle = ellipse_geometry(
        fit_ellipse_direct(in_plane[:, 0], in_plane[:, 1]))
    return centre, axis_a, axis_b, angle, ramanujan2(axis_a, axis_b)


def main():
    """Draw the gallery and print the per-slice area ratios."""
    run_name = sys.argv[1] if len(sys.argv) > 1 else "output_test6"
    step_cm = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    cloud, solid, scale, planes = load_run(run_name)
    lower_z, upper_z = planes[0]["centroid"][2], planes[-1]["centroid"][2]
    heights_cm = np.arange(0.0, (upper_z - lower_z) * scale + 0.01, step_cm)

    columns = 5
    rows = math.ceil(len(heights_cm) / columns)
    figure, axes_grid = plt.subplots(rows, columns,
                                     figsize=(3.4 * columns, 3.4 * rows))
    axes_list = np.atleast_1d(axes_grid).ravel()

    print(f'{"h cm":>5s} {"pts":>4s} {"girth":>6s} {"a/b":>5s} '
          f'{"ellipse":>8s} {"mesh":>8s} {"ratio":>6s}  loops')
    total_ellipse, total_mesh = 0.0, 0.0
    for axes, height_cm in zip(axes_list, heights_cm):
        height = lower_z + height_cm / scale
        in_plane = slice_points(cloud, height, scale)
        axes.set_aspect("equal")
        axes.grid(alpha=0.2)
        axes.tick_params(labelsize=6)

        if len(in_plane) < 12:
            axes.set_title(f"h {height_cm:.0f} cm — {len(in_plane)} pts", fontsize=8)
            continue

        centre, axis_a, axis_b, angle, girth = fit_ring(in_plane)
        centred = in_plane - centre
        axes.scatter(centred[:, 0], centred[:, 1], s=5, color="#7a8b99", alpha=0.8)

        theta = np.linspace(0, 2 * math.pi, 200)
        ellipse_x = axis_a * np.cos(theta)
        ellipse_y = axis_b * np.sin(theta)
        axes.plot(ellipse_x * math.cos(angle) - ellipse_y * math.sin(angle),
                  ellipse_x * math.sin(angle) + ellipse_y * math.cos(angle),
                  color="#0b5fa5", linewidth=1.4)

        ellipse_area = math.pi * axis_a * axis_b
        mesh_area = 0.0
        # The points were plotted as in_plane - centre, where in_plane is already
        # absolute xy in cm. Bring the mesh loops into that same frame: absolute
        # cm (no offset from mesh_section), then subtract the same ellipse centre.
        loops = mesh_section(solid, height, scale, np.zeros(2))
        loops = [loop - centre for loop in loops]
        for loop in loops:
            closed = np.vstack([loop, loop[:1]])
            axes.plot(closed[:, 0], closed[:, 1], color="#b3261e", linewidth=1.6)
            mesh_area += polygon_area(loop)
        ratio = mesh_area / ellipse_area if ellipse_area else float("nan")
        total_ellipse += ellipse_area
        total_mesh += mesh_area

        flag = "  <-- bulge" if ratio > 1.10 else ""
        axes.set_title(f"h {height_cm:.0f}  girth {girth:.1f}  "
                       f"mesh/pts {ratio:.2f}{flag}",
                       fontsize=8, color="#b3261e" if ratio > 1.10 else "#1a1a1a")
        print(f"{height_cm:5.1f} {len(in_plane):4d} {girth:6.2f} "
              f"{axis_a / axis_b:5.2f} {ellipse_area:8.2f} {mesh_area:8.2f} "
              f"{ratio:6.3f}  {len(loops)}{flag}")

    for axes in axes_list[len(heights_cm):]:
        axes.axis("off")

    print(f"\nsummed over slices: mesh section area / ellipse area = "
          f"{total_mesh / total_ellipse:.3f}  "
          f"({100 * (total_mesh / total_ellipse - 1):+.1f}% extra from the wrap)")

    figure.suptitle(f"{run_name} — every {step_cm:.0f} cm from the lower band: "
                    "grey = cleaned points, blue = ellipse fit, red = mesh section",
                    fontsize=11)
    figure.tight_layout(rect=[0, 0, 1, 0.97])
    output = f"{PROJECT_ROOT}/{run_name}/ring_gallery.png"
    figure.savefig(output, dpi=110)
    print(output)


if __name__ == "__main__":
    main()
