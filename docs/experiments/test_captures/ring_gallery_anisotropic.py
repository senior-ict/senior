"""Per-slice gallery comparing the sphere MLS against two ellipsoid kernels.

Four columns at every height, each after the pipeline's own 4x pass:

    today            what the run wrote: 4x MLS, alpha-wrapped
    4 -> sphere 16   the stacked candidate from the sweep, Poisson-wrapped
    4 -> N12 / T6    ellipsoid long along the normal, short in the tangent plane
    4 -> N6 / T12    the reverse: short along the normal, long in the tangent

All three candidates are wrapped by Poisson so the columns differ only in the
second MLS pass. Titles carry girth and mesh/points area ratio; the last page
tabulates the volumes.

    python docs/experiments/test_captures/ring_gallery_anisotropic.py
"""
import math
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = str(HERE.parents[2])
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, str(HERE))

from pipeline.core.meshcut import apply_marker_cut_to_mesh  # noqa: E402
from pipeline.ghost import ghost_voxel_downsample, mls_project, normal_aware_filter  # noqa: E402
from mls_anisotropic import mls_project_ellipsoid  # noqa: E402
from mls_radius_sweep import load_capture, poisson_solid  # noqa: E402
from ring_gallery_before_after import (TRUTH, before_state, draw_panel,  # noqa: E402
                                       height_range)

OUTPUT = HERE / "ring_gallery_anisotropic.pdf"
PANELS_PER_PAGE = 4
INK, MUTED = "#1a1a1a", "#5a5a5a"

# (label, second-pass kind, parameters). The first pass is always the 4x sphere.
VARIANTS = [
    ("4 → sphere 16", "sphere", {"radius_mult": 16.0}),
    ("4 → N12 / T6", "ellipsoid", {"normal_mult": 12.0, "tangent_mult": 6.0}),
    ("4 → N6 / T12", "ellipsoid", {"normal_mult": 6.0, "tangent_mult": 12.0}),
]


def first_pass(run_name):
    """The ghost chain up to and including the pipeline's 4x MLS, in run space."""
    cluster, voxel_size, normal_scale, rotation, scale_cm, cube_volume, planes = load_capture(run_name)
    points = np.asarray(cluster.points, dtype=np.float32)
    colours = (np.zeros((len(points), 3), dtype=np.uint8) if not cluster.has_colors()
               else (np.clip(np.asarray(cluster.colors, dtype=np.float32), 0, 1) * 255).astype(np.uint8))
    points, colours = ghost_voxel_downsample(points, colours, voxel_size)
    points, colours = normal_aware_filter(points, colours, normal_scale)
    points, colours, _ = mls_project(points, colours, radius_mult=4.0, polynomial=True, verbose=False)
    return np.asarray(points, dtype=np.float64), colours, rotation, scale_cm, cube_volume, planes


def second_pass(points, colours, kind, parameters):
    """Apply one candidate second pass and return the points."""
    if kind == "sphere":
        projected, _, _ = mls_project(points, colours, polynomial=True, verbose=False, **parameters)
        return np.asarray(projected, dtype=np.float64)
    projected, _ = mls_project_ellipsoid(points, **parameters)
    return np.asarray(projected, dtype=np.float64)


def solid_volume(solid, planes, cube_volume):
    """Span volume when planes exist, else the whole object, scaled like Stage 6."""
    if solid is None:
        return float("nan")
    if len(planes) >= 2:
        cut, case = apply_marker_cut_to_mesh(solid, planes)
        if case != "case_2_between":
            return float("nan")
        return abs(cut.volume) * (1000.0 / cube_volume)
    return abs(solid.volume) * (1000.0 / cube_volume)


def build_variants(run_name):
    """Today's state plus each candidate: (label, levelled cloud, solid, chi, volume)."""
    base_points, colours, rotation, scale_cm, cube_volume, planes = first_pass(run_name)
    today_cloud, today_solid = before_state(run_name)
    states = [("today", today_cloud, today_solid, None, solid_volume(today_solid, planes, cube_volume))]
    for label, kind, parameters in VARIANTS:
        levelled = second_pass(base_points, colours, kind, parameters) @ rotation.T
        solid, euler = poisson_solid(levelled)
        states.append((label, levelled, solid, euler, solid_volume(solid, planes, cube_volume)))
    return states, scale_cm, planes


def gallery(pdf, run_name):
    """Draw every height of one object and return its summary rows."""
    states, scale_cm, planes = build_variants(run_name)
    lower_z, heights_cm = height_range(run_name, planes, states[0][1], scale_cm)

    ratios = {label: [] for label, *_ in states}
    girths = {label: [] for label, *_ in states}
    for page_start in range(0, len(heights_cm), PANELS_PER_PAGE):
        page_heights = heights_cm[page_start:page_start + PANELS_PER_PAGE]
        figure, axes_grid = plt.subplots(len(page_heights), len(states),
                                         figsize=(3.0 * len(states), 2.6 * len(page_heights) + 0.6))
        axes_grid = np.atleast_2d(axes_grid)
        for row, height_cm in enumerate(page_heights):
            height = lower_z + height_cm / scale_cm
            for column, (label, cloud, solid, _, _) in enumerate(states):
                girth, ratio = draw_panel(axes_grid[row, column], cloud, solid, height,
                                          scale_cm, f"h {height_cm:.0f}  {label}")
                girths[label].append(girth)
                ratios[label].append(ratio)
        figure.suptitle(TRUTH[run_name]["label"], fontsize=10, color=INK)
        figure.tight_layout(rect=[0, 0, 1, 0.96])
        pdf.savefig(figure)
        plt.close(figure)

    rows = []
    for label, _, _, euler, volume in states:
        rows.append((run_name, label, float(np.nanmean(girths[label])),
                     float(np.nanmean(ratios[label])), euler, volume))
    return rows


def summary_page(pdf, rows):
    """Final page: one line per variant per object."""
    figure = plt.figure(figsize=(11.69, 8.27))
    figure.text(0.06, 0.92, "Sphere vs ellipsoid second pass — summary",
                fontsize=16, weight="bold", color=INK)
    lines = [f'{"object":22s} {"variant":16s} {"mean girth":>11s} {"mesh/pts":>9s} '
             f'{"poisson χ":>10s} {"volume":>9s}', "-" * 82]
    for run_name, label, girth, ratio, euler, volume in rows:
        chi = "alpha" if euler is None else str(euler)
        lines.append(f"{run_name:22s} {label:16s} {girth:11.2f} {ratio:9.3f} {chi:>10s} {volume:9.1f}")
    lines += ["", "truth: test6 span 1398.6 cm3 (tape);  can girth 18.5, cylinder bound 394.9",
              "mesh/pts near 1.00 = the solid sits on the points; girth unchanged = anatomy kept"]
    figure.text(0.06, 0.84, "\n".join(lines), fontsize=9, family="monospace",
                color=INK, va="top", linespacing=1.5)
    pdf.savefig(figure)
    plt.close(figure)


def main():
    """Render the gallery for both objects and print the summary."""
    rows = []
    with PdfPages(OUTPUT) as pdf:
        for run_name in TRUTH:
            rows.extend(gallery(pdf, run_name))
        summary_page(pdf, rows)
    print(f'{"object":22s} {"variant":16s} {"girth":>7s} {"mesh/pts":>9s} {"chi":>6s} {"volume":>9s}')
    for run_name, label, girth, ratio, euler, volume in rows:
        print(f"{run_name:22s} {label:16s} {girth:7.2f} {ratio:9.3f} "
              f"{'alpha' if euler is None else euler:>6} {volume:9.1f}")
    print(OUTPUT)


if __name__ == "__main__":
    main()
