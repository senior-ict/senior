"""Per-slice gallery of two real pipeline runs, side by side, from disk.

Unlike ring_gallery_before_after.py, nothing is rebuilt here: both columns are
what the pipeline itself wrote -- its cleaned cloud (03_clean/objects/leg.ply)
and its watertight solid (05_watertight/mesh/leg_no_cut.ply). So a difference
between the columns is a difference between two cold runs, not between a run
and an offline replay.

    python ring_gallery_two_runs.py output_test6 output_test6_mls16 test6_pair.pdf
"""
import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
import trimesh
from matplotlib.backends.backend_pdf import PdfPages

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = str(HERE.parents[2])
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, str(HERE))

from ring_gallery_before_after import draw_panel, height_range  # noqa: E402

PANELS_PER_PAGE = 5
INK = "#1a1a1a"


def load_run(run_name):
    """Cleaned cloud, watertight solid, cm-per-unit scale, cut planes, and the log."""
    debug = pathlib.Path(PROJECT_ROOT) / run_name / "for_debug"
    cloud = np.asarray(o3d.io.read_point_cloud(str(debug / "03_clean/objects/leg.ply")).points)
    solid = trimesh.load(str(debug / "05_watertight/mesh/leg_no_cut.ply"), process=False)
    box = trimesh.load(str(debug / "05_watertight/mesh/box.ply"), process=False)
    scale_cm = (1000.0 / box.volume) ** (1.0 / 3.0)
    planes_path = debug / "03_clean/debug/cutting_line_levelled.json"
    planes = []
    if planes_path.exists():
        planes = sorted(json.load(open(planes_path))["markers"],
                        key=lambda plane: plane["centroid"][2])
    return cloud, solid, scale_cm, planes


def reported_volume(run_name):
    """The limb volume Stage 6 wrote, and its method, from volumes.csv."""
    import csv
    path = pathlib.Path(PROJECT_ROOT) / run_name / "for_debug/06_volume/volumes.csv"
    with open(path) as handle:
        for row in csv.DictReader(handle):
            if row["name"].startswith("leg_cut"):
                return float(row["real_vol_cm3"]), row["method"]
    return float("nan"), "?"


def main():
    """Draw the two runs side by side and print per-slice numbers."""
    left_run, right_run, output_name = sys.argv[1], sys.argv[2], sys.argv[3]
    left_cloud, left_solid, scale_cm, planes = load_run(left_run)
    right_cloud, right_solid, _, _ = load_run(right_run)
    lower_z, heights_cm = height_range(left_run, planes, left_cloud, scale_cm)
    output = HERE / output_name

    print(f'{"h":>4s} {left_run + " girth":>26s} {"m/p":>5s} {right_run + " girth":>30s} {"m/p":>5s}')
    left_ratios, right_ratios = [], []
    with PdfPages(output) as pdf:
        for page_start in range(0, len(heights_cm), PANELS_PER_PAGE):
            page_heights = heights_cm[page_start:page_start + PANELS_PER_PAGE]
            figure, axes_grid = plt.subplots(len(page_heights), 2,
                                             figsize=(11.69, 2.35 * len(page_heights) + 0.6))
            axes_grid = np.atleast_2d(axes_grid)
            for row, height_cm in enumerate(page_heights):
                height = lower_z + height_cm / scale_cm
                left_girth, left_ratio = draw_panel(
                    axes_grid[row, 0], left_cloud, left_solid, height, scale_cm,
                    f"h {height_cm:.0f}  {left_run}")
                right_girth, right_ratio = draw_panel(
                    axes_grid[row, 1], right_cloud, right_solid, height, scale_cm,
                    f"h {height_cm:.0f}  {right_run}")
                left_ratios.append(left_ratio)
                right_ratios.append(right_ratio)
                print(f"{height_cm:4.0f} {left_girth:26.2f} {left_ratio:5.2f} "
                      f"{right_girth:30.2f} {right_ratio:5.2f}")
            left_volume, left_method = reported_volume(left_run)
            right_volume, right_method = reported_volume(right_run)
            figure.suptitle(f"{left_run}: {left_volume:.1f} cm³ ({left_method})    vs    "
                            f"{right_run}: {right_volume:.1f} cm³ ({right_method})",
                            fontsize=10, color=INK)
            figure.tight_layout(rect=[0, 0, 1, 0.96])
            pdf.savefig(figure)
            plt.close(figure)
    print(f"mean mesh/points: {left_run} {np.nanmean(left_ratios):.3f}   "
          f"{right_run} {np.nanmean(right_ratios):.3f}")
    print(output)


if __name__ == "__main__":
    main()
