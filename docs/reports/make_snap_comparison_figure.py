"""Compare the two ways of putting a stray point back onto the reference cube.

The mender currently moves a point along whichever axis it is furthest out on.
That is right for a point sitting off the middle of a face and wrong for a
point sitting off a corner, which is outside on two axes at once: fixing the
larger one leaves it hanging off the other.

  left    the two moves drawn on a square, with one point off a face and one
          off a corner
  right   measured on test2_champ's 5,418 reference points: how far each point
          still sits from the cube's surface after each kind of move

    python docs/reports/make_snap_comparison_figure.py

Needs `output_test2_champ`, which is not committed.
"""
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from matplotlib.patches import FancyArrowPatch, Rectangle

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core import box_mending  # noqa: E402
from pipeline.core.cube_fit import fit_cube  # noqa: E402

RUN = PROJECT_ROOT / "output_test2_champ"
OUTPUT = HERE / "figures/2026-10-10_snap_comparison.png"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8882"
RULE = "#e4e2dc"
ALONG_AXIS_COLOUR = "#c2410c"
NEAREST_POINT_COLOUR = "#2a78d6"
HALF_SIDE_CM = 5.0

# Two stray points: one off the middle of a face, one off a corner.
STRAY_POINTS = (("off a face", 7.6, 1.2), ("off a corner", 7.4, 7.0))


def load_cube_points():
    """The reference cube's cleaned points, before any mending."""
    cloud = o3d.io.read_point_cloud(str(RUN / "for_debug/03_clean/objects/box.ply"))
    return np.asarray(cloud.points)


def move_along_biggest_axis(local_points, half_side_cm):
    """Today's move: push the point in along whichever axis it is furthest out on."""
    axis = np.argmax(np.abs(local_points), axis=1)
    rows = np.arange(len(local_points))
    moved = local_points.copy()
    moved[rows, axis] = np.sign(local_points[rows, axis]) * half_side_cm
    return moved


def move_to_nearest_surface_point(local_points, half_side_cm):
    """The other move: put the point on the closest spot of the cube's surface."""
    moved = np.clip(local_points, -half_side_cm, half_side_cm)
    is_inside = np.all(np.abs(local_points) <= half_side_cm, axis=1)
    inside_rows = np.flatnonzero(is_inside)
    if len(inside_rows):
        # A point already inside has no clamping to do, so send it out to its
        # nearest face, which is the axis it is closest to the wall on.
        axis = np.argmax(np.abs(local_points[inside_rows]), axis=1)
        moved[inside_rows, axis] = (np.sign(local_points[inside_rows, axis])
                                    * half_side_cm)
    return moved


def distance_to_surface_millimetres(local_points, half_side_cm):
    """How far each point sits from the cube's surface, inside or outside, in mm."""
    offsets = np.abs(local_points) - half_side_cm
    outside = np.linalg.norm(np.maximum(offsets, 0.0), axis=1)
    inside = np.minimum(offsets.max(axis=1), 0.0)
    return np.abs(outside + inside) * 10.0


def draw_the_two_moves(axes):
    """Left panel: both moves drawn on a square, for a face point and a corner point."""
    axes.add_patch(Rectangle((-HALF_SIDE_CM, -HALF_SIDE_CM), 2 * HALF_SIDE_CM,
                             2 * HALF_SIDE_CM, facecolor="#f4f2ec", edgecolor=INK,
                             lw=2.2))
    for label, stray_x, stray_y in STRAY_POINTS:
        stray = np.array([[stray_x, stray_y, 0.0]])
        along_axis = move_along_biggest_axis(stray, HALF_SIDE_CM)[0]
        nearest = move_to_nearest_surface_point(stray, HALF_SIDE_CM)[0]

        axes.plot(stray_x, stray_y, marker="o", markersize=10, color=INK)
        axes.text(stray_x + 0.35, stray_y + 0.25, label, fontsize=11, color=INK)

        axes.add_patch(FancyArrowPatch((stray_x, stray_y),
                                       (along_axis[0], along_axis[1]),
                                       arrowstyle="-|>", mutation_scale=15,
                                       color=ALONG_AXIS_COLOUR, lw=2.0))
        axes.plot(along_axis[0], along_axis[1], marker="o", markersize=8,
                  color=ALONG_AXIS_COLOUR)
        axes.add_patch(FancyArrowPatch((stray_x, stray_y), (nearest[0], nearest[1]),
                                       arrowstyle="-|>", mutation_scale=15,
                                       color=NEAREST_POINT_COLOUR, lw=2.0, ls="--"))
        axes.plot(nearest[0], nearest[1], marker="o", markersize=8,
                  color=NEAREST_POINT_COLOUR)

        still_out = distance_to_surface_millimetres(along_axis.reshape(1, 3),
                                                    HALF_SIDE_CM)[0]
        if still_out > 0.01:
            axes.text(along_axis[0] - 4.8, along_axis[1] + 0.7,
                      f"still {still_out:.0f} mm\noff the cube", fontsize=10,
                      color=ALONG_AXIS_COLOUR, linespacing=1.5)

    axes.plot([], [], color=ALONG_AXIS_COLOUR, lw=2.0,
              label="move along the biggest axis (today)")
    axes.plot([], [], color=NEAREST_POINT_COLOUR, lw=2.0, ls="--",
              label="move to the nearest point on the cube")
    axes.legend(fontsize=10, frameon=False, loc="lower center",
                bbox_to_anchor=(0.5, -0.13))
    axes.set_xlim(-6.2, 11.5)
    axes.set_ylim(-6.6, 9.6)
    axes.set_aspect("equal")
    axes.axis("off")
    axes.set_title("the two moves, on a square", fontsize=12.5, color=INK, loc="left",
                   pad=8)


def draw_leftover_distances(axes, distances_by_method):
    """Right panel: how far points still sit from the cube after each kind of move."""
    names = list(distances_by_method)
    colours = [INK_MUTED, ALONG_AXIS_COLOUR, NEAREST_POINT_COLOUR]
    positions = np.arange(len(names))
    means = []
    for name in names:
        means.append(float(distances_by_method[name].mean()))
    axes.barh(positions, means, color=colours, height=0.5)
    for position, name in zip(positions, names):
        distances = distances_by_method[name]
        over_one = 100 * float(np.mean(distances > 1.0))
        axes.text(0.03, position + 0.40,
                  f"mean {distances.mean():.3f} mm   ·   worst {distances.max():.1f} mm"
                  f"   ·   {over_one:.1f}% still over 1 mm",
                  va="center", fontsize=10.5, color=INK)
    axes.set_yticks(positions)
    axes.set_yticklabels(names, fontsize=10.5)
    axes.set_ylim(len(names) - 0.3, -0.6)
    axes.set_xlim(0, 2.5)
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)
    axes.spines["left"].set_color(RULE)
    axes.spines["bottom"].set_color(RULE)
    axes.tick_params(colors=INK_SECONDARY, labelsize=10)
    axes.set_xlabel("mean distance from the cube's surface afterwards (mm)",
                    fontsize=10.5, color=INK_SECONDARY)
    axes.set_title("measured on test2_champ's 5,418 reference points", fontsize=12.5,
                   color=INK, loc="left", pad=8)


def main():
    """Draw both panels into one figure."""
    points = load_cube_points()
    fit = fit_cube(points)
    scale_cm_per_unit = box_mending.REFERENCE_SIDE_CM / fit["side"]
    local_points_cm = box_mending.to_cube_frame(points, fit) * scale_cm_per_unit

    tolerance_cm = box_mending.DEFAULT_TOLERANCE_MM / 10.0
    snapped_today, _ = box_mending.snap_onto_faces(local_points_cm, HALF_SIDE_CM,
                                                   tolerance_cm)
    moved_to_nearest = move_to_nearest_surface_point(local_points_cm, HALF_SIDE_CM)
    distances_by_method = {
        "left alone": distance_to_surface_millimetres(local_points_cm, HALF_SIDE_CM),
        "along the biggest axis\n(what the pipeline does)":
            distance_to_surface_millimetres(snapped_today, HALF_SIDE_CM),
        "to the nearest point\non the cube":
            distance_to_surface_millimetres(moved_to_nearest, HALF_SIDE_CM)}

    figure = plt.figure(figsize=(14.5, 5.8), facecolor=SURFACE)
    figure.text(0.035, 0.955,
                "Two ways to put a stray point back on the cube", fontsize=19,
                weight="bold", color=INK, va="top")
    figure.text(0.035, 0.895,
                "A point off the middle of a face is fixed by either move. A point off "
                "a corner is outside on two axes at once, so moving it along just the "
                "biggest one leaves it hanging off the other.",
                fontsize=11.5, color=INK_SECONDARY, va="top")

    draw_the_two_moves(figure.add_axes([0.04, 0.12, 0.36, 0.68]))
    draw_leftover_distances(figure.add_axes([0.48, 0.28, 0.48, 0.48]),
                            distances_by_method)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, dpi=140, facecolor=SURFACE)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
