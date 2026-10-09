"""Draw the one-page explainer for what snapping the reference cube does, and what it costs.

Four panels, left to right, top to bottom:

  1  the cube as it reconstructs, seen from the side, against the ideal cube
     that fits it -- the 2 mm of fuzz the mending is aimed at
  2  every point's distance past its nearest face, before and after snapping
  3  each capture's volume error, as it stands and after the mending
  4  the three options averaged over all seven captures

The numbers are from the 9 October 2026 reruns and the snap-and-remeasure
sweep; the limb mesh is untouched in every case, so only the reference's
contribution to the scale moves.
"""
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

from pipeline.core.cube_fit import fit_cube  # noqa: E402

OUTPUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-10-09_box_mending.png"
EXAMPLE_RUN = PROJECT_ROOT / "output_test2_keng"

SURFACE = "#fcfcfb"
INK = "#1a1a1a"
AS_IS_COLOUR = "#8a8882"
SNAPPED_COLOUR = "#2a78d6"
IDEAL_COLOUR = "#b3261e"

# capture, truth cm3, as reconstructed, snapped at 1 mm, the fitted cube itself
RESULTS = [
    ("test6", 1398.6, 1495.8, 1472.3, 1495.0),
    ("test2_keng", 1420.2, 1517.5, 1506.1, 1523.6),
    ("test5", 2070.0, 2169.3, 2152.1, 2187.6),
    ("0_right", 1830.0, 1740.3, 1720.0, 1802.1),
    ("1_left", 1600.0, 1588.9, 1495.8, 1681.6),
    ("6_left", 2800.0, 2644.0, 2629.1, 2630.0),
    ("2_left", 1050.0, 1169.0, 1162.9, 1175.0),
]
TRUTH_UNCERTAINTY = {"test2_keng": 2.5}   # the band tilted between measuring and shooting


def cube_frame_points(points, fit):
    """Points in the cube's own frame, centred, in centimetres."""
    yaw = np.radians(fit["yaw_degrees"])
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    centre_x, centre_y = fit["centre"]
    centre_z = fit["bottom"] + fit["side"] / 2.0
    shifted_x = points[:, 0] - centre_x
    shifted_y = points[:, 1] - centre_y
    local_x = shifted_x * cosine - shifted_y * sine
    local_y = shifted_x * sine + shifted_y * cosine
    return np.column_stack([local_x, local_y, points[:, 2] - centre_z])


def signed_face_offset(local, half_side):
    """Signed distance past the nearest face (+ outside, - inside), same units as the input."""
    magnitudes = np.abs(local)
    nearest_axis = np.argmax(magnitudes, axis=1)
    return magnitudes[np.arange(len(local)), nearest_axis] - half_side


def load_example():
    """One run's cube points in centimetres, its half side, and the offsets before and after."""
    cloud = o3d.io.read_point_cloud(str(EXAMPLE_RUN / "for_debug/03_clean/objects/box.ply"))
    points = np.asarray(cloud.points)
    mesh = trimesh.load(str(EXAMPLE_RUN / "for_debug/05_watertight/mesh/box.ply"), process=False)
    scale = (1000.0 / abs(mesh.volume)) ** (1.0 / 3.0)
    fit = fit_cube(points)
    local_cm = cube_frame_points(points, fit) * scale
    half_side_cm = fit["side"] / 2.0 * scale
    offsets_mm = signed_face_offset(local_cm, half_side_cm) * 10
    snapped_mm = np.where(np.abs(offsets_mm) > 1.0, 0.0, offsets_mm)
    return local_cm, half_side_cm, offsets_mm, snapped_mm


def draw_slice_panel(axes, local_cm, half_side_cm):
    """A thin vertical slab of the cube seen from the side, with the ideal outline on top."""
    slab = local_cm[np.abs(local_cm[:, 1]) < 0.4]
    axes.scatter(slab[:, 0], slab[:, 2], s=4, color=AS_IS_COLOUR, label="reconstructed points")
    square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]) * half_side_cm
    axes.plot(square[:, 0], square[:, 1], color=IDEAL_COLOUR, linewidth=2,
              label="the cube that fits them")
    axes.set_aspect("equal")
    axes.set_xlabel("cm")
    axes.set_ylabel("cm")
    axes.set_title("1 — the cube reconstructs fuzzy, not wrong",
                   fontsize=12.5, weight="bold", loc="left")
    axes.legend(fontsize=9, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=2)
    axes.grid(alpha=0.2)


def draw_snap_panel(axes, offsets_mm, snapped_mm):
    """Distance past the nearest face, before and after the snap."""
    bins = np.linspace(-6, 6, 70)
    axes.hist(offsets_mm, bins=bins, color=AS_IS_COLOUR, label="as reconstructed")
    axes.hist(snapped_mm, bins=bins, color=SNAPPED_COLOUR, alpha=0.85, label="after snapping")
    axes.axvline(0.0, color=IDEAL_COLOUR, linewidth=1.4)
    axes.set_xlabel("distance past the nearest face (mm)")
    axes.set_ylabel("points")
    axes.set_title("2 — snapping flattens the fuzz onto the faces",
                   fontsize=12.5, weight="bold", loc="left")
    axes.legend(fontsize=9, frameon=False)
    axes.grid(alpha=0.2)


def draw_capture_panel(axes):
    """Per capture: the error as it stands and after the mending."""
    positions = np.arange(len(RESULTS))
    as_is = [100 * (row[2] / row[1] - 1) for row in RESULTS]
    snapped = [100 * (row[3] / row[1] - 1) for row in RESULTS]
    width = 0.38
    axes.bar(positions - width / 2, as_is, width, color=AS_IS_COLOUR, label="as it stands")
    axes.bar(positions + width / 2, snapped, width, color=SNAPPED_COLOUR, label="box mended")
    for index, row in enumerate(RESULTS):
        uncertainty = TRUTH_UNCERTAINTY.get(row[0])
        if uncertainty:
            axes.errorbar(index - width / 2, as_is[index], yerr=uncertainty, color=INK,
                          capsize=4, linewidth=1.2, zorder=5)
    axes.axhline(0.0, color=INK, linewidth=1.0)
    axes.set_xticks(positions)
    axes.set_xticklabels([row[0] for row in RESULTS], fontsize=10, rotation=20, ha="right")
    axes.set_ylabel("volume error against truth (%)")
    axes.set_title("3 — what it does to each capture", fontsize=12.5, weight="bold", loc="left")
    axes.legend(fontsize=9, frameon=False, loc="upper left")
    axes.grid(alpha=0.2, axis="y")
    axes.set_axisbelow(True)


def draw_summary_panel(axes):
    """The three options averaged over every capture."""
    labels = ["as it stands", "box mended\n(snap at 1 mm)", "reference replaced\nby a perfect cube"]
    columns = (2, 3, 4)
    colours = (AS_IS_COLOUR, SNAPPED_COLOUR, IDEAL_COLOUR)
    mean_absolute = []
    mean_signed = []
    for column in columns:
        errors = np.array([100 * (row[column] / row[1] - 1) for row in RESULTS])
        mean_absolute.append(np.abs(errors).mean())
        mean_signed.append(errors.mean())
    positions = np.arange(len(labels))
    axes.bar(positions, mean_absolute, 0.55, color=colours)
    for position, (absolute, signed) in enumerate(zip(mean_absolute, mean_signed)):
        axes.text(position, absolute + 0.12, f"{absolute:.1f}%", ha="center", fontsize=12,
                  weight="bold", color=INK)
        axes.text(position, absolute / 2, f"bias\n{signed:+.1f}%", ha="center", va="center",
                  fontsize=10, color="white")
    axes.set_xticks(positions)
    axes.set_xticklabels(labels, fontsize=10)
    axes.set_ylabel("mean error ignoring sign, 7 captures (%)")
    axes.set_ylim(0, max(mean_absolute) * 1.25)
    axes.set_title("4 — and to the average: no better", fontsize=12.5, weight="bold", loc="left")
    axes.grid(alpha=0.2, axis="y")
    axes.set_axisbelow(True)


def main():
    """Draw all four panels into one page."""
    local_cm, half_side_cm, offsets_mm, snapped_mm = load_example()

    figure = plt.figure(figsize=(14.5, 9.6), facecolor=SURFACE)
    figure.suptitle("Mending the reference cube: what it is, and why we are not adopting it",
                    fontsize=16, weight="bold", y=0.975)
    figure.text(0.5, 0.942,
                "The 10 cm cube sets the scale for every measurement. It reconstructs as a correct cube "
                "with about 2 mm of fuzz on its faces.",
                fontsize=11.5, ha="center", color="#52514e")
    figure.text(0.5, 0.917,
                "Snapping that fuzz flat fixes the shape — and does not fix the volume.",
                fontsize=11.5, ha="center", color="#52514e")

    draw_slice_panel(figure.add_axes([0.065, 0.54, 0.36, 0.33]), local_cm, half_side_cm)
    draw_snap_panel(figure.add_axes([0.575, 0.54, 0.38, 0.33]), offsets_mm, snapped_mm)
    draw_capture_panel(figure.add_axes([0.065, 0.09, 0.44, 0.33]))
    draw_summary_panel(figure.add_axes([0.60, 0.09, 0.355, 0.33]))

    for axes in figure.get_axes():
        axes.set_facecolor(SURFACE)
        for spine in ("top", "right"):
            axes.spines[spine].set_visible(False)

    figure.text(0.065, 0.015,
                "Every row uses the same limb mesh; only the reference changes. "
                "test2_keng's truth carries ±2.5% (the band tilted between measuring and shooting).",
                fontsize=10, color="#52514e")
    figure.savefig(OUTPUT, dpi=110, facecolor=SURFACE)
    print(OUTPUT)


if __name__ == "__main__":
    main()
