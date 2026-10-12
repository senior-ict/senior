"""Show where the skeleton step's chunks sit on test6's leg, and how one chunk is flattened.

  left    the leg's cleaned points seen from the side, with the two bands, the
          chunk range (-8% to 108% of the band span) and every chunk boundary;
          percentages count from the lower band (0%) to the upper band (100%)
  middle  one chunk (85% up) zoomed in from the side: its thickness in cm
  right   the same chunk seen from above: every point in it, height ignored

    python docs/reports/make_chunk_explainer.py
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

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.limb_skeleton import slice_skeleton  # noqa: E402

RUN = PROJECT_ROOT / "work/test6_skel_off"
OUTPUT = HERE / "2026-09-21_chunk_explainer.png"
EXAMPLE_FRACTION = 0.85
SURFACE = "#fcfcfb"
POINT_COLOUR = "#9aa5ae"
CHUNK_COLOUR = "#2a78d6"
BAND_COLOUR = "#2e9d57"
OUTSIDE_COLOUR = "#efeeea"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"


def main():
    """Draw the three panels."""
    box = trimesh.load(str(RUN / "05_watertight/mesh/box.ply"), process=False)
    scale_cm = (1000.0 / abs(box.volume)) ** (1.0 / 3.0)
    planes = json.load(open(RUN / "03_clean/debug/cutting_line_levelled.json"))["markers"]
    band_heights = sorted(plane["centroid"][2] for plane in planes)
    lower, upper = band_heights[0], band_heights[-1]
    points = np.asarray(o3d.io.read_point_cloud(str(RUN / "03_clean/objects/leg.ply")).points)
    slices = slice_skeleton(points, lower, upper)

    centre_xy = np.nanmean(slices["skeleton"], axis=0)
    side_x_cm = (points[:, 0] - centre_xy[0]) * scale_cm
    height_cm = (points[:, 2] - lower) * scale_cm
    span_cm = (upper - lower) * scale_cm
    edges_cm = (slices["slice_edges"] - lower) * scale_cm
    chunk_thickness_cm = edges_cm[1] - edges_cm[0]

    example_height = lower + EXAMPLE_FRACTION * (upper - lower)
    example_index = int(np.digitize([example_height], slices["slice_edges"])[0] - 1)
    in_example = slices["inside_range"] & (slices["slice_of_point"] == example_index)

    figure = plt.figure(figsize=(15, 7.2), facecolor=SURFACE)

    # Left: the whole leg from the side.
    side_axes = figure.add_axes([0.04, 0.08, 0.36, 0.84])
    side_axes.axhspan(height_cm.min() - 5, edges_cm[0], color=OUTSIDE_COLOUR, lw=0)
    side_axes.axhspan(edges_cm[-1], height_cm.max() + 5, color=OUTSIDE_COLOUR, lw=0)
    side_axes.scatter(side_x_cm, height_cm, s=0.4, color=POINT_COLOUR, lw=0)
    for edge in edges_cm:
        side_axes.axhline(edge, color=CHUNK_COLOUR, linewidth=0.35, alpha=0.6)
    side_axes.axhspan(edges_cm[example_index], edges_cm[example_index + 1], color=CHUNK_COLOUR, alpha=0.55, lw=0)
    for band_height, label in ((0.0, "lower band = 0%"), (span_cm, "upper band = 100%")):
        side_axes.axhline(band_height, color=BAND_COLOUR, linewidth=2.2)
        side_axes.text(10.5, band_height + 0.4, label, color=BAND_COLOUR, fontsize=11, weight="bold")
    for percent in (25, 50, 75):
        side_axes.text(10.5, percent / 100 * span_cm, f"{percent}%", color=INK_SECONDARY, fontsize=10,
                       va="center")
    side_axes.text(10.5, edges_cm[0] - 0.9, "−8%  (chunks start)", color=CHUNK_COLOUR, fontsize=10, va="center")
    side_axes.text(10.5, edges_cm[-1] + 0.9, "108%  (chunks end)", color=CHUNK_COLOUR, fontsize=10, va="center")
    side_axes.text(10.5, edges_cm[example_index] + 0.25, f"chunk shown ({EXAMPLE_FRACTION:.0%})",
                   color=CHUNK_COLOUR, fontsize=10, va="bottom", weight="bold")
    side_axes.text(-11.5, edges_cm[-1] + 3.0, "not chunked:\nMLS only", color=INK_SECONDARY, fontsize=10)
    side_axes.text(-11.5, edges_cm[0] - 6.5, "not chunked:\nMLS only (foot)", color=INK_SECONDARY, fontsize=10)
    side_axes.set_xlim(-12, 26)
    side_axes.set_ylim(height_cm.min() - 1, height_cm.max() + 1)
    side_axes.set_aspect("equal")
    side_axes.set_xticks([])
    side_axes.set_ylabel("height above the lower band (cm)", fontsize=11)
    for spine in ("top", "right", "bottom"):
        side_axes.spines[spine].set_visible(False)
    side_axes.set_title(f"60 chunks between −8% and 108%, each {chunk_thickness_cm:.2f} cm tall", fontsize=12)

    # Middle: the example chunk from the side, zoomed in.
    zoom_axes = figure.add_axes([0.45, 0.30, 0.20, 0.44])
    zoom_axes.scatter(side_x_cm[in_example], height_cm[in_example], s=6, color=CHUNK_COLOUR, lw=0)
    zoom_axes.axhline(edges_cm[example_index], color=INK_SECONDARY, linewidth=0.8, linestyle="--")
    zoom_axes.axhline(edges_cm[example_index + 1], color=INK_SECONDARY, linewidth=0.8, linestyle="--")
    zoom_axes.set_ylim(edges_cm[example_index] - 0.4, edges_cm[example_index + 1] + 0.4)
    zoom_axes.set_xlim(-6.5, 6.5)
    zoom_axes.set_xticks([])
    zoom_axes.set_ylabel("height (cm)", fontsize=10)
    zoom_axes.set_title(f"that chunk from the side\n{chunk_thickness_cm:.2f} cm tall, {in_example.sum()} points",
                        fontsize=11)
    figure.text(0.665, 0.52, "squash flat\n(ignore height)  →", fontsize=11, color=INK, va="center")

    # Right: the example chunk from above.
    top_axes = figure.add_axes([0.77, 0.24, 0.21, 0.56])
    chunk_xy_cm = (points[in_example, :2] - slices["skeleton"][example_index]) * scale_cm
    top_axes.scatter(chunk_xy_cm[:, 0], chunk_xy_cm[:, 1], s=7, color=CHUNK_COLOUR, lw=0)
    top_axes.plot([0], [0], marker="+", markersize=13, markeredgewidth=2, color="#b3261e")
    top_axes.set_aspect("equal")
    top_axes.set_xlim(-6.5, 6.5)
    top_axes.set_ylim(-6.5, 6.5)
    top_axes.set_xticks([])
    top_axes.set_yticks([])
    top_axes.set_title("the same chunk from above\n+ = skeleton centre; the curve is fitted here", fontsize=11)

    figure.savefig(OUTPUT, dpi=100, facecolor=SURFACE)
    print(OUTPUT)


if __name__ == "__main__":
    main()
