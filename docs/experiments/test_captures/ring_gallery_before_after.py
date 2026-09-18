"""Per-slice before/after gallery: today's pipeline against the MLS candidate.

For every 2 cm of height between the bands, two panels side by side:

    left   today   — 4x MLS cloud, and the alpha-wrapped solid's cross-section
    right  after   — 4x then 16x MLS cloud, and the Poisson solid's cross-section

Grey points are the cleaned cloud, blue is the ellipse fitted through them,
red is the mesh section. Each title carries the girth and the ratio of mesh
section area to ellipse area, so the wrap's excess is read off directly.

The "after" cloud and mesh are rebuilt here with the same functions the sweep
used; the "before" ones are what the run wrote to disk.

    python docs/experiments/test_captures/ring_gallery_before_after.py
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
from matplotlib.backends.backend_pdf import PdfPages

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = str(HERE.parents[2])
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, str(HERE))

from pipeline.core.crosssection import plane_basis  # noqa: E402
from mls_radius_sweep import clean_with_radius, load_capture, poisson_solid  # noqa: E402
from ring_gallery import fit_ring, mesh_section, polygon_area, slice_points  # noqa: E402

CANDIDATE_PASSES = (4.0, 16.0)
STEP_CM = 2.0
PANELS_PER_PAGE = 5
OUTPUT = HERE / "ring_gallery_before_after.pdf"

GREY, BLUE, RED, INK, MUTED = "#7a8b99", "#0b5fa5", "#b3261e", "#1a1a1a", "#5a5a5a"

TRUTH = {
    "output_test6": {"span_cm3": 1398.6, "label": "test6 — nearly hairless shin"},
    "output_fanta_orange": {"span_cm3": None, "label": "fanta_orange — rigid can, girth 18.5"},
}


def before_state(run_name):
    """Today's cleaned cloud and watertight solid, straight from the run."""
    debug = f"{PROJECT_ROOT}/{run_name}/for_debug"
    cloud = np.asarray(o3d.io.read_point_cloud(
        f"{debug}/03_clean/objects/leg.ply").points)
    solid = trimesh.load(f"{debug}/05_watertight/mesh/leg_no_cut.ply", process=False)
    return cloud, solid


def after_state(run_name):
    """The candidate: 4x then 16x MLS, wrapped by Poisson. Returns (cloud, solid, chi)."""
    cluster, voxel_size, normal_scale, rotation, _, _, _ = load_capture(run_name)
    cleaned = clean_with_radius(cluster, voxel_size, normal_scale, CANDIDATE_PASSES)
    levelled = cleaned @ rotation.T
    solid, euler = poisson_solid(levelled)
    return levelled, solid, euler


def height_range(run_name, planes, cloud, scale_cm):
    """Heights to draw: between the bands, or the whole object for the can."""
    if len(planes) >= 2:
        lower_z = planes[0]["centroid"][2]
        top_cm = (planes[-1]["centroid"][2] - lower_z) * scale_cm
        return lower_z, np.arange(0.0, top_cm + 0.01, STEP_CM)
    lower_z = cloud[:, 2].min()
    top_cm = (cloud[:, 2].max() - lower_z) * scale_cm
    return lower_z, np.arange(1.0, top_cm - 0.5, STEP_CM)


def draw_panel(axes, cloud, solid, height, scale_cm, heading):
    """One cross-section: points, ellipse, mesh outline. Returns (girth, ratio)."""
    axes.set_aspect("equal")
    axes.grid(alpha=0.2)
    axes.tick_params(labelsize=6)

    in_plane = slice_points(cloud, height, scale_cm)
    if len(in_plane) < 12:
        axes.set_title(f"{heading}: {len(in_plane)} pts", fontsize=8)
        return float("nan"), float("nan")

    centre, axis_a, axis_b, angle, girth = fit_ring(in_plane)
    centred = in_plane - centre
    axes.scatter(centred[:, 0], centred[:, 1], s=4, color=GREY, alpha=0.8)

    theta = np.linspace(0, 2 * math.pi, 200)
    ellipse_x, ellipse_y = axis_a * np.cos(theta), axis_b * np.sin(theta)
    axes.plot(ellipse_x * math.cos(angle) - ellipse_y * math.sin(angle),
              ellipse_x * math.sin(angle) + ellipse_y * math.cos(angle),
              color=BLUE, linewidth=1.3)

    ellipse_area = math.pi * axis_a * axis_b
    mesh_area = 0.0
    if solid is not None:
        for loop in mesh_section(solid, height, scale_cm, np.zeros(2)):
            loop = loop - centre
            closed = np.vstack([loop, loop[:1]])
            axes.plot(closed[:, 0], closed[:, 1], color=RED, linewidth=1.5)
            mesh_area += polygon_area(loop)
    ratio = mesh_area / ellipse_area if ellipse_area and mesh_area else float("nan")

    colour = RED if ratio > 1.10 else INK
    axes.set_title(f"{heading}   girth {girth:.1f}   mesh/pts {ratio:.2f}",
                   fontsize=8, color=colour)
    return girth, ratio


def cover_page(pdf, summaries):
    """A first page stating what the two columns are and the totals."""
    figure = plt.figure(figsize=(11.69, 8.27))
    figure.text(0.06, 0.92, "Per-slice before / after — the MLS candidate",
                fontsize=17, weight="bold", color=INK)
    figure.text(0.06, 0.86,
                "left column   today: 4× MLS, then the alpha-shape fallback (Poisson tunnelled)\n"
                "right column  candidate: 4× then 16× MLS, then Poisson (closes, χ = 2)\n\n"
                "grey = cleaned points   blue = ellipse through them   red = the solid's section\n"
                "mesh/pts = section area over ellipse area; above 1.10 is titled in red",
                fontsize=10, color=INK, va="top", linespacing=1.6)
    y_position = 0.60
    for line in summaries:
        figure.text(0.06, y_position, line, fontsize=9.5, family="monospace", color=INK)
        y_position -= 0.03
    figure.text(0.06, 0.06, "docs/experiments/test_captures/ring_gallery_before_after.py",
                fontsize=7, color=MUTED)
    pdf.savefig(figure)
    plt.close(figure)


def gallery_pages(pdf, run_name):
    """Draw every slice of one object across as many pages as needed."""
    _, _, _, _, scale_cm, cube_volume_units, planes = load_capture(run_name)
    before_cloud, before_solid = before_state(run_name)
    after_cloud, after_solid, euler = after_state(run_name)
    lower_z, heights_cm = height_range(run_name, planes, before_cloud, scale_cm)

    rows = []
    for page_start in range(0, len(heights_cm), PANELS_PER_PAGE):
        page_heights = heights_cm[page_start:page_start + PANELS_PER_PAGE]
        figure, axes_grid = plt.subplots(len(page_heights), 2,
                                         figsize=(11.69, 2.35 * len(page_heights) + 0.6))
        axes_grid = np.atleast_2d(axes_grid)
        for row_index, height_cm in enumerate(page_heights):
            height = lower_z + height_cm / scale_cm
            before = draw_panel(axes_grid[row_index, 0], before_cloud, before_solid,
                                height, scale_cm, f"h {height_cm:.0f}  today")
            after = draw_panel(axes_grid[row_index, 1], after_cloud, after_solid,
                               height, scale_cm, f"h {height_cm:.0f}  4→16 + Poisson")
            rows.append((height_cm, *before, *after))
        figure.suptitle(f"{TRUTH[run_name]['label']}   (after: Poisson χ = {euler})",
                        fontsize=10, color=INK)
        figure.tight_layout(rect=[0, 0, 1, 0.96])
        pdf.savefig(figure)
        plt.close(figure)

    before_ratio = np.nanmean([row[2] for row in rows])
    after_ratio = np.nanmean([row[4] for row in rows])
    summary = (f"{run_name:22s}  mesh/pts  today {before_ratio:.3f}  ->  "
               f"candidate {after_ratio:.3f}    (Poisson χ after = {euler})")
    print(summary)
    print(f'{"h":>4s} {"girth before":>13s} {"ratio":>6s} {"girth after":>12s} {"ratio":>6s}')
    for height_cm, girth_b, ratio_b, girth_a, ratio_a in rows:
        print(f"{height_cm:4.0f} {girth_b:13.2f} {ratio_b:6.2f} {girth_a:12.2f} {ratio_a:6.2f}")
    return summary


def main():
    """Build the PDF: cover with totals, then the galleries."""
    summaries = []
    with PdfPages(OUTPUT) as pdf:
        # The cover needs the totals, so the galleries are rendered to a
        # scratch PDF first and the cover page written last... except PdfPages
        # appends in order. Simplest honest approach: compute galleries into
        # this PDF and put the totals on the final page instead.
        for run_name in TRUTH:
            summaries.append(gallery_pages(pdf, run_name))
        cover_page(pdf, summaries)
    print(OUTPUT)


if __name__ == "__main__":
    main()
