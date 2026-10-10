"""Show how box mending decides which face each of the cube's points belongs to.

Three panels, all run live on a real capture:

  left    the yaw sweep that finds the cube's pose. The cube is symmetric
          every quarter turn, so 0-90 degrees is swept in 2-degree steps and
          the best few angles are polished. Nothing about faces is known
          before this; the sweep is what pins the cube down.
  middle  the points coloured by the face each was assigned to. The rule is
          one line: in the cube's own frame, whichever of x, y, z has the
          largest magnitude names the face, and its sign names the side.
          Neighbouring faces and edges are never consulted.
  right   how decisive each assignment is: the gap between a point's largest
          and second-largest coordinate. A large gap means the point sits
          squarely on one face; a gap near zero means it sits on an edge,
          where either face is an equally good answer.

    python docs/reports/make_face_assignment_figure.py

Needs `output_test2_champ`, a run whose cube has not been mended (outputs are
never committed).
"""
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core import box_mending  # noqa: E402
from pipeline.core.cube_fit import (  # noqa: E402
    YAW_STEP_DEGREES, fit_cube, guess_cube_at_yaw, mean_squared_distance)

RUN = PROJECT_ROOT / "output_test2_champ"
OUTPUT = HERE / "figures/2026-10-10_face_assignment.png"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8882"
RULE = "#e4e2dc"
ACCENT = "#2a78d6"
WARM = "#c2410c"
FACE_COLOURS = {"x+": "#2a78d6", "x-": "#7fb0e8", "y+": "#1b7f5a", "y-": "#7cc3a5",
                "top": "#b07d2a", "bottom": "#c2410c"}
NEAR_EDGE_MILLIMETRES = 2.0


def load_cube_points():
    """The reference cube's cleaned points from the run, before any mending."""
    path = RUN / "for_debug/03_clean/objects/box.ply"
    cloud = o3d.io.read_point_cloud(str(path))
    return np.asarray(cloud.points)


def sweep_yaw(points):
    """The fit's cost at every yaw angle it tries, before any local polishing."""
    yaw_degrees = np.arange(0.0, 90.0, YAW_STEP_DEGREES)
    costs = []
    for one_yaw_degrees in yaw_degrees:
        yaw = np.radians(one_yaw_degrees)
        centre_x, centre_y, bottom, side = guess_cube_at_yaw(points, yaw)
        costs.append(mean_squared_distance(points, yaw, centre_x, centre_y, bottom, side))
    return yaw_degrees, np.array(costs)


def isometric(corner_x, corner_y, corner_z):
    """Project a point of the cube onto the page, seen from a corner above it."""
    horizontal = (corner_x - corner_y) * np.cos(np.radians(30))
    vertical = (corner_x + corner_y) * np.sin(np.radians(30)) + corner_z
    return horizontal, vertical


def face_label(axis_index, side_sign):
    """The name box_mending gives a face, from its axis and which side it is on."""
    return box_mending.FACE_NAMES[(int(axis_index), int(side_sign))]


def tidy_axes(axes, title):
    """House style: no top or right spine, receding axis lines, left-aligned title."""
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)
    axes.spines["left"].set_color(RULE)
    axes.spines["bottom"].set_color(RULE)
    axes.tick_params(colors=INK_SECONDARY, labelsize=9)
    axes.set_title(title, fontsize=12, color=INK, loc="left", pad=8)


def draw_yaw_sweep(axes, yaw_degrees, costs, best_yaw_degrees):
    """Panel 1: the cost of every yaw the sweep tries, and where the fit settled."""
    axes.plot(yaw_degrees, costs, color=ACCENT, lw=2)
    axes.axvline(best_yaw_degrees, color=WARM, lw=1.8, ls="--")
    axes.annotate(f"the fit settles at {best_yaw_degrees:.0f}°",
                  xy=(best_yaw_degrees, costs.min()),
                  xytext=(best_yaw_degrees - 34, costs.max() * 0.62),
                  fontsize=10, color=WARM,
                  arrowprops=dict(arrowstyle="-|>", color=WARM, lw=1.2))
    tidy_axes(axes, "1 · sweep the yaw to find the cube")
    axes.set_xlabel("yaw of the trial cube (degrees)", fontsize=10, color=INK_SECONDARY)
    axes.set_ylabel("mean squared distance to its surface", fontsize=10,
                    color=INK_SECONDARY)
    axes.set_xlim(0, 90)


def draw_assigned_faces(axes, local_points_cm, axis_index, side_sign, half_side_cm):
    """Panel 2: every point drawn in the cube's frame, coloured by the face it got."""
    for face_axis in (0, 1, 2):
        for face_side in (1, -1):
            on_face = (axis_index == face_axis) & (side_sign == face_side)
            if not on_face.any():
                continue
            name = face_label(face_axis, face_side)
            screen_x, screen_y = isometric(local_points_cm[on_face, 0],
                                           local_points_cm[on_face, 1],
                                           local_points_cm[on_face, 2])
            axes.scatter(screen_x, screen_y, s=1.6, color=FACE_COLOURS[name], lw=0,
                         label=f"{name} ({on_face.sum():,})")

    # The fitted cube's twelve edges, so the assignment can be read against it.
    corners = []
    for corner_x in (-half_side_cm, half_side_cm):
        for corner_y in (-half_side_cm, half_side_cm):
            for corner_z in (-half_side_cm, half_side_cm):
                corners.append((corner_x, corner_y, corner_z))
    for first_index, first in enumerate(corners):
        for second in corners[first_index + 1:]:
            shared_axes = 0
            for value_a, value_b in zip(first, second):
                if value_a == value_b:
                    shared_axes += 1
            if shared_axes == 2:
                start_x, start_y = isometric(*first)
                end_x, end_y = isometric(*second)
                axes.plot([start_x, end_x], [start_y, end_y], color=INK, lw=0.9,
                          alpha=0.55, zorder=0)

    axes.set_aspect("equal")
    axes.axis("off")
    axes.set_title("2 · the largest coordinate names the face", fontsize=12, color=INK,
                   loc="left", pad=8)
    axes.legend(fontsize=8.5, frameon=False, loc="lower center", ncol=3,
                bbox_to_anchor=(0.5, -0.09), handletextpad=0.1, columnspacing=0.9,
                markerscale=5)


def draw_margin_histogram(axes, margin_millimetres):
    """Panel 3: how far ahead the winning face was, for every point."""
    axes.hist(margin_millimetres, bins=70, range=(0, 50), color="#c9c6be")
    axes.axvline(NEAR_EDGE_MILLIMETRES, color=WARM, lw=1.8)
    near_edge_share = 100 * np.mean(margin_millimetres < NEAR_EDGE_MILLIMETRES)
    axes.text(0.97, 0.86,
              f"{near_edge_share:.1f}% of points are within\n"
              f"{NEAR_EDGE_MILLIMETRES:.0f} mm of an edge, where both\n"
              f"faces are equally good answers\n\n"
              f"median lead: {np.median(margin_millimetres):.0f} mm",
              transform=axes.transAxes, ha="right", va="top", fontsize=10,
              color=INK_SECONDARY, linespacing=1.7)
    tidy_axes(axes, "3 · how decisive each assignment is")
    axes.set_xlabel("how far the winning coordinate leads the runner-up (mm)",
                    fontsize=10, color=INK_SECONDARY)
    axes.set_ylabel("points", fontsize=10, color=INK_SECONDARY)


def main():
    """Draw the three panels into one figure."""
    points = load_cube_points()
    fit = fit_cube(points)
    scale_cm_per_unit = box_mending.REFERENCE_SIDE_CM / fit["side"]
    half_side_cm = box_mending.REFERENCE_SIDE_CM / 2.0
    local_points_cm = box_mending.to_cube_frame(points, fit) * scale_cm_per_unit
    axis_index, side_sign = box_mending.nearest_face(local_points_cm)

    magnitudes = np.abs(local_points_cm)
    ordered = np.sort(magnitudes, axis=1)
    margin_millimetres = (ordered[:, 2] - ordered[:, 1]) * 10.0

    yaw_degrees, costs = sweep_yaw(points)

    figure = plt.figure(figsize=(15.5, 5.6), facecolor=SURFACE)
    figure.text(0.035, 0.955, "How each point is told which face it is on", fontsize=19,
                weight="bold", color=INK, va="top")
    figure.text(0.035, 0.895,
                "test2_champ's reference cube, 5,418 points. The faces are not found "
                "from edges or from neighbouring faces — the cube's pose is fitted "
                "first, and then each point is judged on its own.",
                fontsize=11.5, color=INK_SECONDARY, va="top")

    draw_yaw_sweep(figure.add_axes([0.045, 0.17, 0.25, 0.60]), yaw_degrees, costs,
                   fit["yaw_degrees"])
    draw_assigned_faces(figure.add_axes([0.355, 0.11, 0.26, 0.70]), local_points_cm,
                        axis_index, side_sign, half_side_cm)
    draw_margin_histogram(figure.add_axes([0.705, 0.17, 0.26, 0.60]), margin_millimetres)

    figure.text(0.035, 0.055,
                "The rule, in full: rotate the point by minus the fitted yaw and move "
                "the cube's centre to the origin, then take whichever of |x|, |y|, |z| "
                "is largest. That axis is the face, and the sign is the side.",
                fontsize=11, color=INK, va="top")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT, dpi=140, facecolor=SURFACE)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
