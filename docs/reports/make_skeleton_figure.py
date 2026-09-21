"""Draw how the limb skeleton step works on test6, for the 21 September meeting deck.

Three panels, all from the pipeline's own code (pipeline/core/limb_skeleton.py):

  left    the Stage 5 leg mesh (skeleton step on), see-through, with the
          skeleton through it: each slice's circle-fit centre (small dots) and
          the smoothed skeleton (red line), plus the two band heights
  middle  one slice near the upper band seen from above: the cleaned points
          before the step, the skeleton centre, the smooth curve, and the 2%
          tolerance band around it
  right   the same slice unrolled: radius against angle, with the fitted wave

    python docs/reports/make_skeleton_figure.py
"""
import json
import math
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.limb_skeleton import (  # noqa: E402
    NEIGHBOUR_SLICES, RADIUS_TOLERANCE_FRACTION, curve_radius, fit_smooth_curve, slice_skeleton)

RUN_BEFORE = PROJECT_ROOT / "work/test6_skel_off"
RUN_AFTER = PROJECT_ROOT / "work/test6_skel_on"
OUTPUT = HERE / "2026-09-21_skeleton_figure.png"
EXAMPLE_FRACTION = 0.85
MESH_TRIANGLES = 9000
SURFACE = "#fcfcfb"
MESH_COLOUR = np.array([0.80, 0.80, 0.78])
SKELETON_COLOUR = "#b3261e"
CENTRE_COLOUR = "#2f3a44"
CURVE_COLOUR = "#2a78d6"
BAND_COLOUR = "#2e9d57"
POINT_COLOUR = "#2f3a44"
TOLERANCE_COLOUR = "#cfe0f6"
INK_SECONDARY = "#52514e"


def cube_scale(stage_root):
    """Centimetres per scene unit, from the reference cube's volume."""
    box = trimesh.load(str(stage_root / "05_watertight/mesh/box.ply"), process=False)
    return (1000.0 / abs(box.volume)) ** (1.0 / 3.0)


def band_heights(stage_root):
    """The lower and upper band heights in scene units."""
    planes = json.load(open(stage_root / "03_clean/debug/cutting_line_levelled.json"))["markers"]
    heights = sorted(plane["centroid"][2] for plane in planes)
    return heights[0], heights[-1]


def shaded_mesh(stage_root):
    """The uncut leg solid, simplified for drawing, as (vertices, triangles)."""
    mesh = o3d.io.read_triangle_mesh(str(stage_root / "05_watertight/mesh/leg_no_cut.ply"))
    simplified = mesh.simplify_quadric_decimation(target_number_of_triangles=MESH_TRIANGLES)
    return np.asarray(simplified.vertices), np.asarray(simplified.triangles)


def draw_mesh_with_skeleton(axes, vertices_cm, triangles, raw_centres_cm, skeleton_cm, lower_cm, upper_cm,
                            example_cm):
    """See-through shaded mesh, the per-slice centres, the smoothed skeleton, and the band heights."""
    light_direction = np.array([0.4, -0.7, 0.6])
    light_direction = light_direction / np.linalg.norm(light_direction)
    corners = vertices_cm[triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    brightness = np.abs((normals / lengths) @ light_direction)
    face_colours = []
    for value in brightness:
        shade = MESH_COLOUR * (0.55 + 0.45 * value)
        face_colours.append((shade[0], shade[1], shade[2], 0.28))
    collection = Poly3DCollection(corners, facecolors=face_colours, edgecolors="none")
    axes.add_collection3d(collection)

    valid_raw = ~np.isnan(raw_centres_cm).any(axis=1)
    axes.scatter(raw_centres_cm[valid_raw, 0], raw_centres_cm[valid_raw, 1], raw_centres_cm[valid_raw, 2],
                 s=3, color="#8a8882", depthshade=False)
    valid_skeleton = ~np.isnan(skeleton_cm).any(axis=1)
    axes.plot(skeleton_cm[valid_skeleton, 0], skeleton_cm[valid_skeleton, 1], skeleton_cm[valid_skeleton, 2],
              color=SKELETON_COLOUR, linewidth=3.2, zorder=10)

    angles = np.linspace(0, 2 * math.pi, 100)
    rings = [(lower_cm, BAND_COLOUR, "lower band"), (upper_cm, BAND_COLOUR, "upper band"),
             (example_cm, CURVE_COLOUR, "slice shown")]
    for height_cm, colour, label in rings:
        closest = int(np.nanargmin(np.abs(skeleton_cm[:, 2] - height_cm)))
        centre = skeleton_cm[closest]
        axes.plot(centre[0] + 6.0 * np.cos(angles), centre[1] + 6.0 * np.sin(angles),
                  np.full_like(angles, height_cm), color=colour, linewidth=1.6)
        axes.text(centre[0] + 7.0, centre[1] - 7.0, height_cm, label, fontsize=10, color=colour)
    top_centre = skeleton_cm[~np.isnan(skeleton_cm).any(axis=1)][-1]
    axes.text(top_centre[0] - 9.0, top_centre[1] + 9.0, top_centre[2] + 2.0, "skeleton", fontsize=10,
              color=SKELETON_COLOUR)

    x_middle = float(np.mean(vertices_cm[:, 0]))
    y_middle = float(np.mean(vertices_cm[:, 1]))
    half_width = 12.0
    axes.set_xlim(x_middle - half_width, x_middle + half_width)
    axes.set_ylim(y_middle - half_width, y_middle + half_width)
    z_bottom = float(vertices_cm[:, 2].min())
    z_top = float(vertices_cm[:, 2].max())
    axes.set_zlim(z_bottom, z_top)
    axes.set_box_aspect((2 * half_width, 2 * half_width, z_top - z_bottom))
    axes.view_init(elev=12, azim=-60)
    axes.set_axis_off()


def example_slice(points, slices, fraction, lower, upper):
    """Points, fit points and centre for one slice, as the pipeline would see them."""
    slice_edges = slices["slice_edges"]
    height = lower + fraction * (upper - lower)
    slice_index = int(np.digitize([height], slice_edges)[0] - 1)
    centre = slices["skeleton"][slice_index]
    members = slices["inside_range"] & (slices["slice_of_point"] == slice_index)
    near_slices = slices["inside_range"] & (np.abs(slices["slice_of_point"] - slice_index) <= NEIGHBOUR_SLICES)
    return points[members, :2] - centre, points[near_slices, :2] - centre


def polar(offsets):
    """Angles in 0..2 pi and radii of 2-D offsets from the centre."""
    angles = np.mod(np.arctan2(offsets[:, 1], offsets[:, 0]), 2 * np.pi)
    radii = np.linalg.norm(offsets, axis=1)
    return angles, radii


def main():
    """Build the three-panel figure."""
    scale_cm = cube_scale(RUN_BEFORE)
    lower, upper = band_heights(RUN_BEFORE)
    points = np.asarray(o3d.io.read_point_cloud(str(RUN_BEFORE / "03_clean/objects/leg.ply")).points)
    slices = slice_skeleton(points, lower, upper)

    slice_centre_heights = (slices["slice_edges"][:-1] + slices["slice_edges"][1:]) / 2.0
    origin = np.array([slices["skeleton"][0, 0], slices["skeleton"][0, 1], lower])
    raw_centres = np.column_stack([slices["raw_centres"], slice_centre_heights])
    skeleton = np.column_stack([slices["skeleton"], slice_centre_heights])
    raw_centres_cm = (raw_centres - origin) * scale_cm
    skeleton_cm = (skeleton - origin) * scale_cm
    vertices, triangles = shaded_mesh(RUN_AFTER)
    vertices_cm = (vertices - origin) * scale_cm
    upper_cm = (upper - lower) * scale_cm

    figure = plt.figure(figsize=(15, 6.2), facecolor=SURFACE)
    mesh_axes = figure.add_axes([-0.02, 0.0, 0.36, 0.97], projection="3d")
    mesh_axes.set_facecolor(SURFACE)
    example_cm = EXAMPLE_FRACTION * upper_cm
    draw_mesh_with_skeleton(mesh_axes, vertices_cm, triangles, raw_centres_cm, skeleton_cm, 0.0, upper_cm,
                            example_cm)
    mesh_axes.set_title("Leg mesh with its skeleton", fontsize=13, pad=0)

    slice_offsets, fit_offsets = example_slice(points, slices, EXAMPLE_FRACTION, lower, upper)
    slice_offsets_cm = slice_offsets * scale_cm
    fit_angles, fit_radii = polar(fit_offsets * scale_cm)
    coefficients = fit_smooth_curve(fit_angles, fit_radii)
    curve_angles = np.linspace(0, 2 * np.pi, 360)
    curve_radii = curve_radius(coefficients, curve_angles)
    inner_radii = curve_radii * (1 - RADIUS_TOLERANCE_FRACTION)
    outer_radii = curve_radii * (1 + RADIUS_TOLERANCE_FRACTION)

    top_axes = figure.add_axes([0.345, 0.12, 0.27, 0.78])
    top_axes.fill(np.concatenate([outer_radii * np.cos(curve_angles), inner_radii[::-1] * np.cos(curve_angles[::-1])]),
                  np.concatenate([outer_radii * np.sin(curve_angles), inner_radii[::-1] * np.sin(curve_angles[::-1])]),
                  color=TOLERANCE_COLOUR, lw=0, zorder=1)
    top_axes.plot(curve_radii * np.cos(curve_angles), curve_radii * np.sin(curve_angles), color=CURVE_COLOUR,
                  linewidth=1.8, zorder=2, label="smooth curve")
    top_axes.scatter(slice_offsets_cm[:, 0], slice_offsets_cm[:, 1], s=6, color=POINT_COLOUR, zorder=3,
                     label="points before the step")
    top_axes.plot([0], [0], marker="+", markersize=14, markeredgewidth=2, color=SKELETON_COLOUR, zorder=4,
                  linestyle="none", label="skeleton centre")
    top_axes.set_aspect("equal")
    top_axes.set_xlim(-7, 7)
    top_axes.set_ylim(-7, 7)
    top_axes.set_xticks([])
    top_axes.set_yticks([])
    top_axes.set_title(f"One slice from above ({EXAMPLE_FRACTION:.0%} up)", fontsize=13)
    top_axes.legend(loc="lower left", fontsize=9, frameon=False)

    slice_angles, slice_radii = polar(slice_offsets_cm)
    unrolled_axes = figure.add_axes([0.66, 0.14, 0.32, 0.74])
    unrolled_axes.fill_between(np.degrees(curve_angles), inner_radii, outer_radii, color=TOLERANCE_COLOUR, lw=0,
                               label="±2% tolerance")
    unrolled_axes.plot(np.degrees(curve_angles), curve_radii, color=CURVE_COLOUR, linewidth=1.8,
                       label="smooth curve (6 waves)")
    unrolled_axes.scatter(np.degrees(slice_angles), slice_radii, s=6, color=POINT_COLOUR, zorder=3,
                          label="points")
    unrolled_axes.annotate("spur: pulled in\nto the blue band", xy=(55, 5.6), xytext=(95, 5.9),
                           fontsize=10, color=INK_SECONDARY,
                           arrowprops={"arrowstyle": "->", "color": INK_SECONDARY, "lw": 0.9})
    unrolled_axes.annotate("gap: new points\nplaced on the curve", xy=(85, 4.95), xytext=(120, 5.3),
                           fontsize=10, color=INK_SECONDARY,
                           arrowprops={"arrowstyle": "->", "color": INK_SECONDARY, "lw": 0.9})
    unrolled_axes.set_xlim(0, 360)
    unrolled_axes.set_xticks([0, 90, 180, 270, 360])
    unrolled_axes.set_xlabel("angle around the skeleton (degrees)", fontsize=11)
    unrolled_axes.set_ylabel("distance from the skeleton (cm)", fontsize=11)
    unrolled_axes.set_title("The same slice unrolled", fontsize=13)
    unrolled_axes.spines["top"].set_visible(False)
    unrolled_axes.spines["right"].set_visible(False)
    unrolled_axes.grid(alpha=0.25)
    unrolled_axes.legend(loc="upper right", fontsize=9, frameon=False)
    unrolled_axes.set_facecolor(SURFACE)

    figure.savefig(OUTPUT, dpi=110, facecolor=SURFACE)
    print(OUTPUT)


if __name__ == "__main__":
    main()
