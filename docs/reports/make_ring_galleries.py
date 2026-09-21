"""Draw the two test6 ring galleries used in the 21 September meeting deck.

One row per run, one column per height between the bands. Dark dots are
Stage 3's cleaned points (drawn on top), red is Stage 5's uncut solid, grey
dashed is the tape circle at the same fraction of the way up. Under each ring
is the outline length against the tape.

    python docs/reports/make_ring_galleries.py

writes 2026-09-21_ring_gallery_versions.png  (v3, v4 after stacked MLS, v4 final)
   and 2026-09-21_ring_gallery_skeleton.png  (v4 final, v4 + limb skeleton)
"""
import csv
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

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "docs/experiments/2026-09_test_captures"))

from ring_gallery import fit_ring, mesh_section, polygon_area, slice_points  # noqa: E402

FRACTIONS = [0.1, 0.5, 0.7, 0.8, 0.9]
TAPE_PROFILE = PROJECT_ROOT / "docs/experiments/2026-09_test_captures/test6_tape_profile.csv"
TAPE_VOLUME_CM3 = 1398.6
RULER_CM = 27.5
WINDOW_HALF_WIDTH_CM = 6.5
POINT_COLOUR = "#2f3a44"
MESH_COLOUR = "#b3261e"
TAPE_COLOUR = "#a3a19b"
SURFACE = "#fcfcfb"

VERSION_RUNS = [
    ("v3 reworked\n4x MLS, alpha wrap", PROJECT_ROOT / "output_test6/for_debug"),
    ("v4 after stacked MLS\n4x + 16x, Poisson", PROJECT_ROOT / "output_test6_mls16/for_debug"),
    ("v4 final\nstacked MLS + pad", PROJECT_ROOT / "output_test6_pad/for_debug"),
]
SKELETON_RUNS = [
    ("v4 final", PROJECT_ROOT / "work/test6_skel_off"),
    ("v4 + skeleton", PROJECT_ROOT / "work/test6_skel_on"),
]


def tape_girth_at(fraction):
    """Tape circumference at this fraction of the way from the lower band to the upper."""
    heights = []
    girths = []
    with open(TAPE_PROFILE) as handle:
        for row in csv.DictReader(handle):
            heights.append(float(row["height_cm"]))
            girths.append(float(row["circumference_cm"]))
    return float(np.interp(fraction * RULER_CM, heights, girths))


def stage6_volume(stage_root):
    """Limb volume Stage 6 reported for this run."""
    with open(stage_root / "06_volume/volumes.csv") as handle:
        for row in csv.DictReader(handle):
            if row["name"].startswith("leg_cut"):
                return float(row["real_vol_cm3"])
    return float("nan")


def load_run(stage_root):
    """Cleaned leg cloud, uncut solid, cube scale in cm per unit, and the two band heights."""
    cloud = np.asarray(o3d.io.read_point_cloud(str(stage_root / "03_clean/objects/leg.ply")).points)
    solid = trimesh.load(str(stage_root / "05_watertight/mesh/leg_no_cut.ply"), process=False)
    box = trimesh.load(str(stage_root / "05_watertight/mesh/box.ply"), process=False)
    scale_cm = (1000.0 / abs(box.volume)) ** (1.0 / 3.0)
    planes = json.load(open(stage_root / "03_clean/debug/cutting_line_levelled.json"))["markers"]
    band_heights = sorted(plane["centroid"][2] for plane in planes)
    return cloud, solid, scale_cm, band_heights


def draw_ring(axes, cloud, solid, scale_cm, height, tape_girth):
    """One slice: tape circle, mesh outline, then the points on top. Returns the outline length in cm."""
    in_plane = slice_points(cloud, height, scale_cm)
    centre, _, _, _, _ = fit_ring(in_plane)

    tape_radius = tape_girth / (2 * math.pi)
    angles = np.linspace(0, 2 * math.pi, 200)
    axes.plot(tape_radius * np.cos(angles), tape_radius * np.sin(angles), color=TAPE_COLOUR,
              linewidth=1.2, linestyle=(0, (3, 2)), zorder=1)

    outline_length = 0.0
    for loop in mesh_section(solid, height, scale_cm, np.zeros(2)):
        closed_loop = np.vstack([loop, loop[:1]]) - centre
        axes.plot(closed_loop[:, 0], closed_loop[:, 1], color=MESH_COLOUR, linewidth=1.6, zorder=2)
        if polygon_area(loop) > 1.0:
            segment_lengths = np.linalg.norm(np.diff(closed_loop, axis=0), axis=1)
            outline_length += float(segment_lengths.sum())

    centred_points = in_plane - centre
    axes.scatter(centred_points[:, 0], centred_points[:, 1], s=3, color=POINT_COLOUR, lw=0, zorder=3)

    axes.set_xlim(-WINDOW_HALF_WIDTH_CM, WINDOW_HALF_WIDTH_CM)
    axes.set_ylim(-WINDOW_HALF_WIDTH_CM, WINDOW_HALF_WIDTH_CM)
    axes.set_aspect("equal")
    axes.set_xticks([])
    axes.set_yticks([])
    return outline_length


def draw_gallery(runs, output_path):
    """One row per run, one column per height, saved as a PNG."""
    row_count = len(runs)
    figure, axes_grid = plt.subplots(row_count, len(FRACTIONS),
                                     figsize=(3.3 * len(FRACTIONS), 2.95 * row_count), facecolor=SURFACE)
    axes_grid = np.atleast_2d(axes_grid)
    for row, (label, stage_root) in enumerate(runs):
        cloud, solid, scale_cm, band_heights = load_run(stage_root)
        volume = stage6_volume(stage_root)
        volume_error = 100 * (volume / TAPE_VOLUME_CM3 - 1)
        axes_grid[row, 0].set_ylabel(f"{label}\n{volume:.0f} cm³ ({volume_error:+.1f}%)", fontsize=13)
        for column, fraction in enumerate(FRACTIONS):
            height = band_heights[0] + fraction * (band_heights[1] - band_heights[0])
            tape_girth = tape_girth_at(fraction)
            axes = axes_grid[row, column]
            outline_length = draw_ring(axes, cloud, solid, scale_cm, height, tape_girth)
            outline_error = 100 * (outline_length / tape_girth - 1)
            axes.set_xlabel(f"outline {outline_length:.1f} cm  {outline_error:+.0f}%", fontsize=12, labelpad=2)
            if row == 0:
                axes.set_title(f"{fraction:.0%} up  (tape {tape_girth:.1f} cm)", fontsize=12)
    figure.tight_layout(pad=0.4, h_pad=0.6, w_pad=0.3)
    figure.savefig(output_path, dpi=90, facecolor=figure.get_facecolor())
    plt.close(figure)
    print(output_path)


def main():
    """Draw both galleries next to this script."""
    draw_gallery(VERSION_RUNS, HERE / "2026-09-21_ring_gallery_versions.png")
    draw_gallery(SKELETON_RUNS, HERE / "2026-09-21_ring_gallery_skeleton.png")


if __name__ == "__main__":
    main()
