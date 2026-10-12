"""Compare a finished run's circumference profile against a tape profile.

The tape gives the circumference at a list of heights above the lower band.
This takes the same heights, slices the cleaned limb cloud there, fits an
ellipse to each slice, and prints both circumferences side by side, so an
error in volume can be read as an error in girth, in length, or in neither.

Heights are measured from the LOWER band plane's centroid and run up the
levelled vertical, because that is where the tape started. The slab around
each height is the same +/- 4 mm Stage 6 uses.

Two lengths are printed as well, and they are different things:

    band separation   the vertical distance between the two band centroids,
                      which is what the tape's span should be compared with
    mesh z extent     the cut mesh's height, which is LARGER whenever the
                      cutting planes are oblique, since an oblique cut leaves
                      a slanted rim

    python docs/experiments/2026-09_test_captures/profile_vs_tape.py <run dir> <tape profile csv>
    python .../profile_vs_tape.py <run dir> <csv> --figure out.png
"""
import argparse
import csv
import json
import math
import pathlib
import sys

import numpy as np
import open3d as o3d
import trimesh

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.crosssection import (ellipse_geometry, fit_ellipse_direct,  # noqa: E402
                                        plane_basis, ramanujan2)

REFERENCE_VOLUME_CM3 = 1000.0
SLAB_HALF_MM = 4.0
MINIMUM_SLAB_POINTS = 40

SURFACE = "#fcfcfb"
TAPE_COLOUR = "#8a8882"
MEASURED_COLOUR = "#2a78d6"


def load_run(run_directory):
    """The cleaned limb points, the cm-per-unit scale, the two band planes, and the cut mesh."""
    run = pathlib.Path(run_directory)
    cloud = o3d.io.read_point_cloud(str(run / "for_debug/03_clean/objects/leg.ply"))
    points = np.asarray(cloud.points)
    box_mesh = trimesh.load(str(run / "for_debug/05_watertight/mesh/box.ply"), process=False)
    linear_scale = (REFERENCE_VOLUME_CM3 / abs(box_mesh.volume)) ** (1.0 / 3.0)
    planes_path = run / "for_debug/03_clean/debug/cutting_line_levelled.json"
    planes = json.load(open(planes_path))["markers"]
    planes = sorted(planes, key=lambda plane: plane["centroid"][2])
    cut_mesh = trimesh.load(str(run / "for_debug/05_watertight/mesh/leg_cut.ply"), process=False)
    return points, linear_scale, planes, cut_mesh


def read_tape_profile(path):
    """[(height_cm, circumference_cm), ...] from a profile CSV, sorted by height."""
    rows = []
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append((float(row["height_cm"]), float(row["circumference_cm"])))
    rows.sort(key=lambda entry: entry[0])
    return rows


def horizontal_slice_circumference(points, height_units, linear_scale):
    """Fit an ellipse to the horizontal slab at this height; returns a dict or None."""
    half_units = (SLAB_HALF_MM / 10.0) / linear_scale
    selected = points[np.abs(points[:, 2] - height_units) <= half_units]
    if len(selected) < MINIMUM_SLAB_POINTS:
        return None
    x_cm = selected[:, 0] * linear_scale
    y_cm = selected[:, 1] * linear_scale
    try:
        coefficients = fit_ellipse_direct(x_cm, y_cm)
        centre, semi_major, semi_minor, _ = ellipse_geometry(coefficients)
    except ValueError:
        return None
    angles = np.arctan2(y_cm - centre[1], x_cm - centre[0])
    occupied_bins = len(set(np.floor((angles + math.pi) / (2 * math.pi / 72)).astype(int)))
    return {"circumference_cm": ramanujan2(semi_major, semi_minor),
            "semi_major_cm": semi_major,
            "semi_minor_cm": semi_minor,
            "coverage": occupied_bins / 72.0,
            "point_count": len(selected)}


def band_separation_cm(planes, linear_scale):
    """The vertical distance between the two band centroids, in centimetres."""
    lower_height = planes[0]["centroid"][2]
    upper_height = planes[-1]["centroid"][2]
    return (upper_height - lower_height) * linear_scale


def plane_tilt_degrees(plane):
    """How far this band plane's normal leans from the vertical, in degrees."""
    normal = np.asarray(plane["normal"], dtype=np.float64)
    normal = normal / np.linalg.norm(normal)
    return math.degrees(math.acos(min(1.0, abs(normal[2]))))


def measure_profile(points, linear_scale, planes, tape_profile):
    """One row per tape height: the tape value and what the cloud reads there."""
    lower_height_units = planes[0]["centroid"][2]
    rows = []
    for height_cm, tape_circumference_cm in tape_profile:
        height_units = lower_height_units + height_cm / linear_scale
        fitted = horizontal_slice_circumference(points, height_units, linear_scale)
        rows.append({"height_cm": height_cm,
                     "tape_cm": tape_circumference_cm,
                     "fitted": fitted})
    return rows


def draw_figure(rows, output_path, title, tape_volume_cm3, measured_volume_cm3):
    """Tape and measured circumference against height, with the error beside it."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    heights = [row["height_cm"] for row in rows]
    tape_values = [row["tape_cm"] for row in rows]
    measured_heights = []
    measured_values = []
    error_heights = []
    error_values = []
    for row in rows:
        if row["fitted"] is None:
            continue
        measured_heights.append(row["height_cm"])
        measured_values.append(row["fitted"]["circumference_cm"])
        error_heights.append(row["height_cm"])
        error_values.append(100 * (row["fitted"]["circumference_cm"] / row["tape_cm"] - 1))

    figure = plt.figure(figsize=(11, 5.6), facecolor=SURFACE)
    profile_axes = figure.add_axes([0.08, 0.12, 0.42, 0.76])
    profile_axes.set_facecolor(SURFACE)
    profile_axes.plot(tape_values, heights, color=TAPE_COLOUR, linewidth=2.2, label="tape")
    profile_axes.plot(measured_values, measured_heights, color=MEASURED_COLOUR,
                      linewidth=2.2, label="pipeline")
    profile_axes.set_xlabel("circumference (cm)", fontsize=11)
    profile_axes.set_ylabel("height above the lower band (cm)", fontsize=11)
    profile_axes.set_title("Profile", fontsize=13, weight="bold", loc="left")
    profile_axes.grid(alpha=0.25)
    profile_axes.set_axisbelow(True)
    profile_axes.legend(fontsize=10, frameon=False, loc="lower right")
    for spine in ("top", "right"):
        profile_axes.spines[spine].set_visible(False)

    error_axes = figure.add_axes([0.58, 0.12, 0.38, 0.76])
    error_axes.set_facecolor(SURFACE)
    error_axes.axvline(0.0, color=TAPE_COLOUR, linewidth=1.2)
    error_axes.plot(error_values, error_heights, color=MEASURED_COLOUR, linewidth=2.2)
    error_axes.set_xlabel("pipeline minus tape (%)", fontsize=11)
    error_axes.set_title("Girth error with height", fontsize=13, weight="bold", loc="left")
    error_axes.grid(alpha=0.25)
    error_axes.set_axisbelow(True)
    for spine in ("top", "right"):
        error_axes.spines[spine].set_visible(False)

    figure.suptitle(f"{title}: tape {tape_volume_cm3:.1f} cm³, pipeline {measured_volume_cm3:.1f} cm³ "
                    f"({100 * (measured_volume_cm3 / tape_volume_cm3 - 1):+.1f}%)",
                    fontsize=13)
    figure.savefig(output_path, dpi=110, facecolor=SURFACE)
    plt.close(figure)
    print(f"figure: {output_path}")


def main():
    """Print the profile comparison for one run, and optionally draw it."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("tape_profile")
    parser.add_argument("--figure", default=None)
    arguments = parser.parse_args()

    points, linear_scale, planes, cut_mesh = load_run(arguments.run)
    tape_profile = read_tape_profile(arguments.tape_profile)
    rows = measure_profile(points, linear_scale, planes, tape_profile)

    tape_span_cm = tape_profile[-1][0] - tape_profile[0][0]
    separation_cm = band_separation_cm(planes, linear_scale)
    mesh_height_cm = cut_mesh.extents[2] * linear_scale
    measured_volume_cm3 = abs(cut_mesh.volume) * linear_scale ** 3

    print(f"run {arguments.run}   scale {linear_scale:.4f} cm/unit")
    print(f"  tape span          {tape_span_cm:.2f} cm")
    print(f"  band separation    {separation_cm:.2f} cm "
          f"({100 * (separation_cm / tape_span_cm - 1):+.1f}% vs the tape)")
    print(f"  mesh z extent      {mesh_height_cm:.2f} cm "
          f"(band planes lean {plane_tilt_degrees(planes[0]):.0f}° and "
          f"{plane_tilt_degrees(planes[-1]):.0f}° from the vertical)")
    print()
    print(f"  {'height':>7}{'tape':>8}{'pipeline':>10}{'error':>9}{'a/b':>7}{'cover':>8}{'pts':>7}")
    errors = []
    for row in rows:
        if row["fitted"] is None:
            print(f"  {row['height_cm']:>7.1f}{row['tape_cm']:>8.1f}{'no fit':>10}")
            continue
        fitted = row["fitted"]
        error_percent = 100 * (fitted["circumference_cm"] / row["tape_cm"] - 1)
        errors.append(error_percent)
        axis_ratio = fitted["semi_major_cm"] / fitted["semi_minor_cm"]
        print(f"  {row['height_cm']:>7.1f}{row['tape_cm']:>8.1f}"
              f"{fitted['circumference_cm']:>10.2f}{error_percent:>8.1f}%"
              f"{axis_ratio:>7.2f}{100 * fitted['coverage']:>7.0f}%{fitted['point_count']:>7}")
    if errors:
        errors = np.array(errors)
        print()
        print(f"  girth error        {errors.mean():+.1f}% mean, "
              f"{np.abs(errors).mean():.1f}% ignoring sign, "
              f"{errors.min():+.1f}% to {errors.max():+.1f}%")

    if arguments.figure:
        from tape_volume import frustum_volume

        draw_figure(rows, arguments.figure, pathlib.Path(arguments.run).name,
                    frustum_volume(tape_profile), measured_volume_cm3)


if __name__ == "__main__":
    main()
