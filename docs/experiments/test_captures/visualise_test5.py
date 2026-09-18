"""Visualise why test5's girth reads high: cross-sections, shell, and profile.

Four panels:
  A, B  the two band cross-sections, with the fitted ellipse and the circle the
        tape says it should be
  C     how thick the surface shell is and which way it leans
  D     circumference at every height up the limb, against the two taped points
"""
import json
import math
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
from pipeline.core.crosssection import fit_slice, plane_basis

RUN = f"{PROJECT_ROOT}/output_test5"
OUTPUT = f"{PROJECT_ROOT}/output_test5/test5_diagnostic.png"

TAPED_GIRTH_CM = {"lower": 22.0, "upper": 32.5}
INK, ACCENT, TAPE, SHELL = "#1a1a1a", "#0b5fa5", "#b3261e", "#7a8b99"


def load_run():
    """The cleaned limb cloud, the scale, and the two cutting planes."""
    cloud = o3d.io.read_point_cloud(f"{RUN}/for_debug/03_clean/objects/leg.ply")
    points = np.asarray(cloud.points)
    box = trimesh.load(f"{RUN}/for_debug/05_watertight/mesh/box.ply", process=False)
    linear_scale = (1000.0 / box.volume) ** (1.0 / 3.0)   # cm per mesh unit
    planes = json.load(open(
        f"{RUN}/for_debug/03_clean/debug/cutting_line_levelled.json"))["markers"]
    planes = sorted(planes, key=lambda plane: plane["centroid"][2])
    return points, linear_scale, planes


def slab_in_plane(points, centroid, normal, linear_scale, half_mm=4.0):
    """The slab of points around one plane, as 2-D coordinates in that plane."""
    basis_u, basis_v, basis_n = plane_basis(normal)
    centroid = np.asarray(centroid, dtype=np.float64)
    selected = points[np.abs((points - centroid) @ basis_n)
                      <= (half_mm / 10.0) / linear_scale]
    local = selected - centroid
    in_plane = np.stack([local @ basis_u, local @ basis_v], axis=1)
    return in_plane * linear_scale          # centimetres


def draw_cross_section(axes, in_plane_cm, fitted, taped_girth_cm, title):
    """Scatter one cross-section with its fitted ellipse and the taped circle."""
    centre = in_plane_cm.mean(axis=0)
    centred = in_plane_cm - centre
    radius_cm = np.linalg.norm(centred, axis=1)

    axes.scatter(centred[:, 0], centred[:, 1], s=9, color=SHELL,
                 alpha=0.75, label=f"{len(centred)} surface points", zorder=2)

    angles = np.linspace(0, 2 * math.pi, 400)
    tilt = math.radians(fitted["tilt_deg"])
    ellipse_x = fitted["a_cm"] * np.cos(angles)
    ellipse_y = fitted["b_cm"] * np.sin(angles)
    axes.plot(ellipse_x * math.cos(tilt) - ellipse_y * math.sin(tilt),
              ellipse_x * math.sin(tilt) + ellipse_y * math.cos(tilt),
              color=ACCENT, linewidth=2.0, zorder=3,
              label=f"fitted ellipse — {fitted['circumference_cm']:.2f} cm")

    taped_radius = taped_girth_cm / (2 * math.pi)
    axes.plot(taped_radius * np.cos(angles), taped_radius * np.sin(angles),
              color=TAPE, linewidth=2.0, linestyle="--", zorder=4,
              label=f"taped circle — {taped_girth_cm:.1f} cm")

    axes.set_aspect("equal")
    axes.set_title(title, fontsize=10, color=INK)
    axes.legend(fontsize=7, loc="lower right", framealpha=0.9)
    axes.grid(alpha=0.2)
    axes.set_xlabel("cm", fontsize=8)
    return radius_cm


def draw_shell(axes, radii_by_band):
    """Histogram of radial offset from the median, for both bands."""
    for label, radius_cm in radii_by_band.items():
        offsets_mm = (radius_cm - np.median(radius_cm)) * 10.0
        axes.hist(offsets_mm, bins=34, alpha=0.55, label=f"{label} band")
    axes.axvline(0, color=INK, linewidth=1.2)
    axes.set_xlabel("radial offset from the median, mm", fontsize=9)
    axes.set_ylabel("points", fontsize=9)
    axes.set_title("the surface is a ~15 mm thick shell, and its tail points INWARD\n"
                   "— so there is no outer halo to trim away",
                   fontsize=10, color=INK)
    axes.legend(fontsize=8)
    axes.grid(alpha=0.2)


def draw_profile(axes, points, linear_scale, planes):
    """Circumference at every height up the limb, against the taped points."""
    heights = points[:, 2]
    low, high = heights.min(), heights.max()
    vertical = np.array([0.0, 0.0, 1.0])

    sample_heights, circumferences = [], []
    for height in np.linspace(low + 0.02, high - 0.02, 40):
        try:
            fitted = fit_slice(points, np.array([0.0, 0.0, height]),
                               vertical, linear_scale)
        except ValueError:
            continue
        if fitted["coverage"] < 0.5:
            continue
        sample_heights.append((height - low) * linear_scale)
        circumferences.append(fitted["circumference_cm"])

    axes.plot(circumferences, sample_heights, color=ACCENT, linewidth=2.0,
              marker="o", markersize=3, label="pipeline, every height")

    for label, plane in zip(("lower", "upper"), planes):
        band_height = (plane["centroid"][2] - low) * linear_scale
        axes.scatter([TAPED_GIRTH_CM[label]], [band_height], s=90, color=TAPE,
                     zorder=5, marker="D",
                     label="taped" if label == "lower" else None)
        axes.annotate(f"  taped {TAPED_GIRTH_CM[label]:.1f}",
                      (TAPED_GIRTH_CM[label], band_height), fontsize=8, color=TAPE)
        axes.axhline(band_height, color=TAPE, linewidth=0.8,
                     linestyle=":", alpha=0.7)

    axes.set_xlabel("circumference, cm", fontsize=9)
    axes.set_ylabel("height above the foot, cm", fontsize=9)
    axes.set_title("the gap widens with height — 0.3 mm of radius at the ankle,\n"
                   "4.2 mm below the knee", fontsize=10, color=INK)
    axes.legend(fontsize=8, loc="lower right")
    axes.grid(alpha=0.2)


def main():
    """Build the four-panel figure."""
    points, linear_scale, planes = load_run()

    figure = plt.figure(figsize=(13.5, 10.5))
    figure.suptitle("test5 — why the reconstructed limb reads fat", fontsize=15,
                    weight="bold", color=INK, x=0.06, ha="left")

    radii_by_band = {}
    for index, (label, plane) in enumerate(zip(("lower", "upper"), planes)):
        in_plane_cm = slab_in_plane(points, plane["centroid"],
                                    plane["normal"], linear_scale)
        fitted = fit_slice(points, np.asarray(plane["centroid"]),
                           np.asarray(plane["normal"]), linear_scale)
        axes = figure.add_subplot(2, 2, index + 1)
        error = (100 * (fitted["circumference_cm"] - TAPED_GIRTH_CM[label])
                 / TAPED_GIRTH_CM[label])
        radii_by_band[label] = draw_cross_section(
            axes, in_plane_cm, fitted, TAPED_GIRTH_CM[label],
            f"{label} band cross-section   ({error:+.1f}%)")

    draw_shell(figure.add_subplot(2, 2, 3), radii_by_band)
    draw_profile(figure.add_subplot(2, 2, 4), points, linear_scale, planes)

    figure.tight_layout(rect=[0, 0, 1, 0.96])
    figure.savefig(OUTPUT, dpi=115)
    print(OUTPUT)


if __name__ == "__main__":
    main()
