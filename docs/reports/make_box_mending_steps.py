"""Draw the step-by-step slide for the box mending stage: what it does to the points, in order.

The companion page (make_box_mending_explainer.py) answers "is it worth
adopting". This one answers "what does it actually do", one step per panel,
on real `5_circumference_calculation_1k` points:

  1  the reference cube's points, seen edge-on
  2  the ideal cube fitted to them
  3  each point marked by how far it sits from its face
  4  the same points after snapping
  5  the mesh built from them, before
  6  the mesh built from them, after

    python docs/reports/make_box_mending_steps.py
"""
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.cube_fit import fit_cube  # noqa: E402

OUTPUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "2026-10-09_box_mending_steps.png"
RUN = PROJECT_ROOT / "output_5_circumference_calculation_1k"
MENDED_MESH = PROJECT_ROOT / "work/5_circumference_calculation_1k_mended/05_watertight/mesh/box.ply"
SLAB_HALF_CM = 0.4
TOLERANCE_MM = 1.0

SURFACE = "#fcfcfb"
INK = "#1a1a1a"
GREY = "#8a8882"
BLUE = "#2a78d6"
RED = "#b3261e"
AMBER = "#e08a1e"


def load_points():
    """The cube's points in its own frame, in centimetres, plus its half side."""
    cloud = o3d.io.read_point_cloud(str(RUN / "for_debug/03_clean/objects/box.ply"))
    points = np.asarray(cloud.points)
    mesh = trimesh.load(str(RUN / "for_debug/05_watertight/mesh/box.ply"), process=False)
    scale = (1000.0 / abs(mesh.volume)) ** (1.0 / 3.0)
    fit = fit_cube(points)
    yaw = np.radians(fit["yaw_degrees"])
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    shifted_x = points[:, 0] - fit["centre"][0]
    shifted_y = points[:, 1] - fit["centre"][1]
    local = np.column_stack([shifted_x * cosine - shifted_y * sine,
                             shifted_x * sine + shifted_y * cosine,
                             points[:, 2] - (fit["bottom"] + fit["side"] / 2.0)])
    return local * scale, fit["side"] / 2.0 * scale


def face_offsets_mm(local_cm, half_side_cm):
    """Signed distance past the nearest face, in millimetres (+ outside, - inside)."""
    magnitudes = np.abs(local_cm)
    nearest_axis = np.argmax(magnitudes, axis=1)
    return (magnitudes[np.arange(len(local_cm)), nearest_axis] - half_side_cm) * 10


def square_outline(half_side_cm):
    """The four corners of the cube's outline in this view, closed."""
    return np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]) * half_side_cm


def style_slab_axes(axes, half_side_cm, title, caption):
    """Common framing for the four point panels."""
    axes.set_facecolor(SURFACE)
    axes.set_aspect("equal")
    axes.set_xlim(-half_side_cm * 1.45, half_side_cm * 1.45)
    axes.set_ylim(-half_side_cm * 1.45, half_side_cm * 1.45)
    axes.set_xticks([])
    axes.set_yticks([])
    axes.set_title(title, fontsize=13, weight="bold", loc="left", color=INK)
    axes.text(0.0, -half_side_cm * 1.38, caption, fontsize=10.5, ha="center", color="#52514e")
    for spine in axes.spines.values():
        spine.set_visible(False)


def draw_mesh(axes, mesh_path, scale, title, caption):
    """A shaded view of one cube mesh."""
    mesh = trimesh.load(str(mesh_path), process=False)
    vertices = mesh.vertices * scale
    vertices = vertices - vertices.mean(axis=0)
    shading = 0.4 + 0.6 * np.clip(mesh.face_normals @ np.array([0.4, 0.5, 0.75]), 0, 1)
    colours = np.column_stack([shading * 0.82, shading * 0.86, shading * 0.92,
                               np.ones(len(shading))])
    axes.add_collection3d(Poly3DCollection(vertices[mesh.faces], facecolors=colours,
                                           edgecolors="none"))
    limit = 7.0
    axes.set_xlim(-limit, limit)
    axes.set_ylim(-limit, limit)
    axes.set_zlim(-limit, limit)
    axes.set_box_aspect((1, 1, 1))
    axes.view_init(elev=16, azim=-58)
    axes.set_axis_off()
    axes.set_title(title, fontsize=13, weight="bold", loc="left", color=INK)
    axes.text2D(0.5, -0.04, caption, fontsize=10.5, ha="center", transform=axes.transAxes,
                color="#52514e")
    return mesh


def main():
    """Lay the six steps out on one page."""
    local_cm, half_side_cm = load_points()
    offsets = face_offsets_mm(local_cm, half_side_cm)
    in_slab = np.abs(local_cm[:, 1]) < SLAB_HALF_CM
    slab = local_cm[in_slab]
    slab_offsets = offsets[in_slab]
    outline = square_outline(half_side_cm)

    too_far_out = slab_offsets > TOLERANCE_MM
    too_far_in = slab_offsets < -TOLERANCE_MM
    close_enough = ~too_far_out & ~too_far_in

    figure = plt.figure(figsize=(16, 9), facecolor=SURFACE)
    figure.suptitle("The box mending stage, step by step", fontsize=19, weight="bold", y=0.975)
    figure.text(0.5, 0.932,
                "The 10 cm cube turns scene units into centimetres, so its shape is worth checking. "
                "Every panel is the same slice through the real 5_circumference_calculation_1k cube, seen edge-on.",
                fontsize=12, ha="center", color="#52514e")

    first = figure.add_axes([0.045, 0.50, 0.21, 0.36])
    first.scatter(slab[:, 0], slab[:, 2], s=5, color=GREY)
    style_slab_axes(first, half_side_cm, "1.  the points we get",
                    "fuzzy faces, rounded corners,\na skirt along the bottom")

    second = figure.add_axes([0.285, 0.50, 0.21, 0.36])
    second.scatter(slab[:, 0], slab[:, 2], s=5, color=GREY)
    second.plot(outline[:, 0], outline[:, 1], color=RED, linewidth=2.4)
    style_slab_axes(second, half_side_cm, "2.  fit a perfect cube",
                    f"one cube, four unknowns:\nside {2 * half_side_cm:.2f} cm, turn, centre")

    third = figure.add_axes([0.525, 0.50, 0.21, 0.36])
    third.scatter(slab[close_enough, 0], slab[close_enough, 2], s=5, color=GREY,
                  label=f"within {TOLERANCE_MM:.0f} mm")
    third.scatter(slab[too_far_out, 0], slab[too_far_out, 2], s=9, color=AMBER, label="too far out")
    third.scatter(slab[too_far_in, 0], slab[too_far_in, 2], s=9, color=BLUE, label="too far in")
    third.plot(outline[:, 0], outline[:, 1], color=RED, linewidth=2.4)
    style_slab_axes(third, half_side_cm, "3.  mark who is off",
                    f"{np.sum(offsets > TOLERANCE_MM):,} out, "
                    f"{np.sum(offsets < -TOLERANCE_MM):,} in,\n"
                    f"{np.sum(np.abs(offsets) <= TOLERANCE_MM):,} already fine")
    third.legend(fontsize=9, frameon=True, framealpha=0.95, edgecolor="none",
                 loc="center", handletextpad=0.4)

    fourth = figure.add_axes([0.765, 0.50, 0.21, 0.36])
    snapped = slab.copy()
    magnitudes = np.abs(snapped)
    nearest_axis = np.argmax(magnitudes, axis=1)
    moving = np.flatnonzero(np.abs(slab_offsets) > TOLERANCE_MM)
    snapped[moving, nearest_axis[moving]] = (np.sign(slab[moving, nearest_axis[moving]])
                                             * half_side_cm)
    fourth.scatter(slab[:, 0], slab[:, 2], s=4, color="#d8d6d0")
    fourth.scatter(snapped[:, 0], snapped[:, 2], s=5, color=BLUE)
    fourth.plot(outline[:, 0], outline[:, 1], color=RED, linewidth=2.4)
    # Draw the biggest moves, so the arrows are long enough to read.
    furthest = moving[np.argsort(-np.abs(slab_offsets[moving]))][:120]
    for index in furthest[::7]:
        fourth.annotate("", xy=(snapped[index, 0], snapped[index, 2]),
                        xytext=(slab[index, 0], slab[index, 2]),
                        arrowprops={"arrowstyle": "-|>", "color": INK, "linewidth": 1.3,
                                    "mutation_scale": 11})
    style_slab_axes(fourth, half_side_cm, "4.  snap them onto the face",
                    "each one moves straight out to\nits own face, nothing else moves")

    scale = 91.667879
    fifth = figure.add_axes([0.085, 0.10, 0.22, 0.32], projection="3d")
    before = draw_mesh(fifth, RUN / "for_debug/05_watertight/mesh/box.ply", scale,
                       "5.  the mesh before", "holes patched by Stage 5, skirt,\nlumpy edges")
    sixth = figure.add_axes([0.355, 0.10, 0.22, 0.32], projection="3d")
    after = draw_mesh(sixth, MENDED_MESH, 91.437563,
                      "6.  the mesh after", "straight edges, flat faces,\nno skirt")

    seventh = figure.add_axes([0.655, 0.115, 0.30, 0.30])
    rows = [("cube fit residual", "2.19 mm", "0.44 mm"),
            ("fill of its own box", "0.775  (warns)", "0.883  (passes)"),
            ("scale", "91.668 cm/unit", "91.438 cm/unit"),
            ("limb volume", "1517.5 cm³", "1506.1 cm³"),
            ("against the tape", "+6.9%", "+6.1%")]
    seventh.axis("off")
    seventh.set_title("7.  what changes", fontsize=13, weight="bold", loc="left", color=INK)
    seventh.text(0.47, 1.0, "before", fontsize=11, weight="bold", color=GREY, ha="center")
    seventh.text(0.84, 1.0, "after", fontsize=11, weight="bold", color=BLUE, ha="center")
    for index, (label, before_value, after_value) in enumerate(rows):
        height = 0.86 - index * 0.175
        seventh.text(0.0, height, label, fontsize=11, color=INK)
        seventh.text(0.47, height, before_value, fontsize=11, color=GREY, ha="center")
        seventh.text(0.84, height, after_value, fontsize=11, color=BLUE, ha="center")
    seventh.text(0.0, -0.08,
                 "The limb mesh never changes — only the scale it is measured with.",
                 fontsize=10.5, color="#52514e")

    print(f"before: volume {abs(before.volume) * scale ** 3:.1f} cm3, "
          f"after: {abs(after.volume) * 91.437563 ** 3:.1f} cm3")
    figure.savefig(OUTPUT, dpi=110, facecolor=SURFACE)
    print(OUTPUT)


if __name__ == "__main__":
    main()
