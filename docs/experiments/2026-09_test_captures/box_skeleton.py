"""Slice the reference cube the way the limb skeleton slices the leg, and see where it is bent.

The leg is sliced into chunks, each chunk gets a centre, and a point that sits
far from its neighbours' radius is pulled back. A cube is rigid, so the slices
cannot teach it a shape -- but they show WHICH way it is wrong:

    centre drift   the slice centres wandering with height is a lean or a shear
    side by slice  growing or shrinking with height is a taper
    yaw by slice   turning with height is a twist
    bow            a face that is fine at its edges and pushed out in the middle

Each horizontal slice of a cube is a square outline, so each slice is fitted
with a square (centre, yaw, half side) using the same point-to-surface distance
the 3-D fit uses, one dimension down. The same is then done along the cube's
own x and y axes, which is the "do it vertically too" half.

Corners are reported but not trusted: they hold the fewest points, are seen
most obliquely, and the smoothing rounds them.

Nothing is written back into the pipeline. This reads a finished run.
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
from scipy.optimize import minimize

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.cube_fit import distance_to_cube_surface, fit_cube  # noqa: E402

REFERENCE_VOLUME_CM3 = 1000.0
SLICE_COUNT = 24
SLICE_MARGIN_FRACTION = 0.06      # skip the very ends, where a face becomes an edge
MINIMUM_SLICE_POINTS = 120
SNAP_TOLERANCE_MM = 2.0

SURFACE = "#fcfcfb"
INK = "#1a1a1a"
BEFORE_COLOUR = "#8a8882"
AFTER_COLOUR = "#2a78d6"
IDEAL_COLOUR = "#b3261e"


def load_box(run_directory):
    """The cleaned reference points (levelled) and the cm-per-unit scale from its mesh."""
    run = pathlib.Path(run_directory)
    points = np.asarray(o3d.io.read_point_cloud(str(run / "for_debug/03_clean/objects/box.ply")).points)
    mesh = trimesh.load(str(run / "for_debug/05_watertight/mesh/box.ply"), process=False)
    scale = (REFERENCE_VOLUME_CM3 / abs(mesh.volume)) ** (1.0 / 3.0)
    return points, scale


def to_cube_frame(points, fit):
    """Points re-expressed with the cube's own axes and its centre at the origin."""
    yaw = np.radians(fit["yaw_degrees"])
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    centre_x, centre_y = fit["centre"]
    centre_z = fit["bottom"] + fit["side"] / 2.0
    shifted_x = points[:, 0] - centre_x
    shifted_y = points[:, 1] - centre_y
    local_x = shifted_x * cosine - shifted_y * sine
    local_y = shifted_x * sine + shifted_y * cosine
    local_z = points[:, 2] - centre_z
    return np.column_stack([local_x, local_y, local_z])


def distance_to_square_outline(local_points, yaw, centre_u, centre_v, half):
    """Each 2-D point's distance to the outline of a square of this half-size, centre and turn."""
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    shifted_u = local_points[:, 0] - centre_u
    shifted_v = local_points[:, 1] - centre_v
    rotated_u = shifted_u * cosine - shifted_v * sine
    rotated_v = shifted_u * sine + shifted_v * cosine
    offsets = np.abs(np.column_stack([rotated_u, rotated_v])) - half
    outside = np.linalg.norm(np.maximum(offsets, 0.0), axis=1)
    inside = np.minimum(offsets.max(axis=1), 0.0)
    return np.abs(outside + inside)


def fit_square(local_points, half_guess):
    """Fit a square outline to one slice; returns (centre_u, centre_v, yaw, half, residual)."""

    def cost_of(values):
        """Mean squared distance to a square described by yaw, centre and half-size."""
        if values[3] <= 0:
            return 1e6
        distances = distance_to_square_outline(local_points, values[0], values[1], values[2], values[3])
        return float(np.mean(distances ** 2))

    start = [0.0, 0.0, 0.0, half_guess]
    polished = minimize(cost_of, start, method="Nelder-Mead",
                        options={"xatol": 1e-7, "fatol": 1e-14, "maxiter": 3000})
    yaw, centre_u, centre_v, half = polished.x
    return centre_u, centre_v, yaw, half, float(np.sqrt(polished.fun))


def slice_along_axis(local_points, axis, half_side, scale):
    """Fit a square to each slice taken perpendicular to this cube axis."""
    other_axes = [index for index in (0, 1, 2) if index != axis]
    low = -half_side * (1.0 - 2 * SLICE_MARGIN_FRACTION)
    high = half_side * (1.0 - 2 * SLICE_MARGIN_FRACTION)
    edges = np.linspace(low, high, SLICE_COUNT + 1)
    rows = []
    for index in range(SLICE_COUNT):
        in_slice = ((local_points[:, axis] >= edges[index])
                    & (local_points[:, axis] < edges[index + 1]))
        selected = local_points[in_slice][:, other_axes]
        if len(selected) < MINIMUM_SLICE_POINTS:
            continue
        centre_u, centre_v, yaw, half, residual = fit_square(selected, half_side)
        rows.append({"position_cm": (edges[index] + edges[index + 1]) / 2.0 * scale,
                     "centre_u_mm": centre_u * scale * 10,
                     "centre_v_mm": centre_v * scale * 10,
                     "side_cm": 2 * half * scale,
                     "yaw_degrees": np.degrees(yaw) % 90.0,
                     "residual_mm": residual * scale * 10,
                     "point_count": len(selected)})
    return rows


def corner_reach(local_points, half_side, scale):
    """Per corner: how far the cloud actually reaches along that corner's diagonal, in cm."""
    directions = []
    for sign_x in (-1, 1):
        for sign_y in (-1, 1):
            for sign_z in (-1, 1):
                directions.append((sign_x, sign_y, sign_z))
    ideal_reach = np.sqrt(3.0) * half_side * scale
    rows = []
    for direction in directions:
        octant = ((np.sign(local_points[:, 0]) == direction[0])
                  & (np.sign(local_points[:, 1]) == direction[1])
                  & (np.sign(local_points[:, 2]) == direction[2]))
        selected = local_points[octant]
        if len(selected) < 20:
            continue
        unit = np.array(direction, dtype=float) / np.sqrt(3.0)
        reach = np.percentile(selected @ unit, 99.0) * scale
        rows.append({"direction": direction, "reach_cm": reach,
                     "ideal_cm": ideal_reach, "point_count": len(selected)})
    return rows


def signed_face_offset(local_points, half_side):
    """Signed distance past the nearest face, in cube units (+ outside, - inside)."""
    distances_to_planes = np.abs(local_points)
    nearest_axis = np.argmax(distances_to_planes, axis=1)
    return distances_to_planes[np.arange(len(local_points)), nearest_axis] - half_side


def snap_to_cube(points, fit, scale, tolerance_mm=SNAP_TOLERANCE_MM):
    """Move every point that sits further than the tolerance from its face back onto it."""
    local = to_cube_frame(points, fit)
    half_side = fit["side"] / 2.0
    offsets = signed_face_offset(local, half_side)
    tolerance = (tolerance_mm / 10.0) / scale
    moving = np.abs(offsets) > tolerance
    nearest_axis = np.argmax(np.abs(local), axis=1)
    moved_local = local.copy()
    target = np.sign(local[np.arange(len(local)), nearest_axis]) * half_side
    moving_rows = np.flatnonzero(moving)
    moved_local[moving_rows, nearest_axis[moving_rows]] = target[moving_rows]
    report = {"moved_in": int(np.sum(moving & (offsets > 0))),
              "moved_out": int(np.sum(moving & (offsets < 0))),
              "untouched": int(np.sum(~moving))}
    return moved_local, report


def draw(run_name, scale, fit, horizontal, vertical_x, vertical_y, corners,
         offsets_before, offsets_after, output_path):
    """Six panels: centre drift, side, twist, slice overlay, corners, and the snap."""
    figure = plt.figure(figsize=(15, 9), facecolor=SURFACE)
    figure.suptitle(f"{run_name}: the reference cube, sliced like the leg "
                    f"(fitted side {fit['side'] * scale:.2f} cm)", fontsize=14)

    drift_axes = figure.add_subplot(2, 3, 1)
    heights = [row["position_cm"] for row in horizontal]
    drift_axes.plot([row["centre_u_mm"] for row in horizontal], heights,
                    color=AFTER_COLOUR, linewidth=2, label="x of the slice centre")
    drift_axes.plot([row["centre_v_mm"] for row in horizontal], heights,
                    color=IDEAL_COLOUR, linewidth=2, label="y of the slice centre")
    drift_axes.axvline(0.0, color=BEFORE_COLOUR, linewidth=1.2)
    drift_axes.set_xlabel("offset from the cube's centre (mm)")
    drift_axes.set_ylabel("height above the cube's middle (cm)")
    drift_axes.set_title("Centre drift — lean or shear", fontsize=12, loc="left")
    drift_axes.legend(fontsize=9, frameon=False)
    drift_axes.grid(alpha=0.25)

    side_axes = figure.add_subplot(2, 3, 2)
    side_axes.plot([row["side_cm"] for row in horizontal], heights, color=AFTER_COLOUR, linewidth=2)
    side_axes.axvline(fit["side"] * scale, color=IDEAL_COLOUR, linewidth=1.5,
                      linestyle=(0, (4, 3)), label="the fitted cube")
    side_axes.set_xlabel("side of the slice (cm)")
    side_axes.set_title("Side by height — taper or bow", fontsize=12, loc="left")
    side_axes.legend(fontsize=9, frameon=False)
    side_axes.grid(alpha=0.25)

    twist_axes = figure.add_subplot(2, 3, 3)
    twist_axes.plot([row["yaw_degrees"] for row in horizontal], heights,
                    color=AFTER_COLOUR, linewidth=2)
    twist_axes.axvline(fit["yaw_degrees"], color=IDEAL_COLOUR, linewidth=1.5, linestyle=(0, (4, 3)))
    twist_axes.set_xlabel("turn of the slice (degrees)")
    twist_axes.set_title("Twist by height", fontsize=12, loc="left")
    twist_axes.grid(alpha=0.25)

    axis_axes = figure.add_subplot(2, 3, 4)
    for rows, label, colour in ((vertical_x, "slices across the cube's x", AFTER_COLOUR),
                                (vertical_y, "slices across the cube's y", IDEAL_COLOUR)):
        axis_axes.plot([row["position_cm"] for row in rows],
                       [row["side_cm"] for row in rows], color=colour, linewidth=2, label=label)
    axis_axes.axhline(fit["side"] * scale, color=BEFORE_COLOUR, linewidth=1.2)
    axis_axes.set_xlabel("position along that axis (cm)")
    axis_axes.set_ylabel("side of the slice (cm)")
    axis_axes.set_title("The same, sliced sideways", fontsize=12, loc="left")
    axis_axes.legend(fontsize=9, frameon=False)
    axis_axes.grid(alpha=0.25)

    corner_axes = figure.add_subplot(2, 3, 5)
    labels = ["".join("+" if value > 0 else "-" for value in row["direction"]) for row in corners]
    reaches = [row["reach_cm"] for row in corners]
    corner_axes.bar(labels, reaches, color=AFTER_COLOUR)
    corner_axes.axhline(corners[0]["ideal_cm"], color=IDEAL_COLOUR, linewidth=1.5,
                        linestyle=(0, (4, 3)), label="a true cube's corner")
    corner_axes.set_ylim(min(reaches) * 0.97, max(max(reaches), corners[0]["ideal_cm"]) * 1.01)
    corner_axes.set_ylabel("reach along the diagonal (cm)")
    corner_axes.set_title("Corners — how far the cloud actually reaches", fontsize=12, loc="left")
    corner_axes.legend(fontsize=9, frameon=False)
    corner_axes.grid(alpha=0.25, axis="y")

    snap_axes = figure.add_subplot(2, 3, 6)
    bins = np.linspace(-8, 8, 80)
    snap_axes.hist(offsets_before, bins=bins, color=BEFORE_COLOUR, alpha=0.85, label="as reconstructed")
    snap_axes.hist(offsets_after, bins=bins, color=AFTER_COLOUR, alpha=0.75, label="after snapping")
    snap_axes.axvline(0.0, color=IDEAL_COLOUR, linewidth=1.2)
    snap_axes.set_xlabel("distance past the nearest face (mm)")
    snap_axes.set_title("Points against the ideal faces", fontsize=12, loc="left")
    snap_axes.legend(fontsize=9, frameon=False)
    snap_axes.grid(alpha=0.25)

    for axes in figure.get_axes():
        axes.set_facecolor(SURFACE)
        for spine in ("top", "right"):
            axes.spines[spine].set_visible(False)
    figure.tight_layout(rect=[0, 0, 1, 0.95])
    figure.savefig(output_path, dpi=105, facecolor=SURFACE)
    plt.close(figure)
    print(f"figure: {output_path}")


def main():
    """Slice one run's reference cube, print what the slices say, and draw it."""
    run_directory = sys.argv[1]
    output_path = sys.argv[2]
    points, scale = load_box(run_directory)
    fit = fit_cube(points)
    half_side = fit["side"] / 2.0
    local = to_cube_frame(points, fit)

    horizontal = slice_along_axis(local, 2, half_side, scale)
    vertical_x = slice_along_axis(local, 0, half_side, scale)
    vertical_y = slice_along_axis(local, 1, half_side, scale)
    corners = corner_reach(local, half_side, scale)

    offsets_before = signed_face_offset(local, half_side) * scale * 10
    snapped_local, report = snap_to_cube(points, fit, scale)
    offsets_after = signed_face_offset(snapped_local, half_side) * scale * 10

    print(f"{pathlib.Path(run_directory).name}: fitted side {fit['side'] * scale:.3f} cm, "
          f"yaw {fit['yaw_degrees']:.2f} deg, residual "
          f"{fit['residual'] * scale * 10:.2f} mm")
    print()
    print("horizontal slices (the leg's chunks, applied to the cube)")
    print(f"  {'height cm':>10}{'side cm':>9}{'dx mm':>8}{'dy mm':>8}{'yaw deg':>9}{'rms mm':>8}{'pts':>7}")
    for row in horizontal:
        print(f"  {row['position_cm']:>10.2f}{row['side_cm']:>9.2f}{row['centre_u_mm']:>8.1f}"
              f"{row['centre_v_mm']:>8.1f}{row['yaw_degrees']:>9.2f}{row['residual_mm']:>8.2f}"
              f"{row['point_count']:>7}")
    sides = np.array([row["side_cm"] for row in horizontal])
    print(f"  side across the slices: {sides.min():.2f} to {sides.max():.2f} cm "
          f"(spread {100 * (sides.max() / sides.min() - 1):.1f}%)")
    print()
    print("corners")
    for row in corners:
        label = "".join("+" if value > 0 else "-" for value in row["direction"])
        print(f"  {label}  reach {row['reach_cm']:.2f} cm against {row['ideal_cm']:.2f} "
              f"({100 * (row['reach_cm'] / row['ideal_cm'] - 1):+.1f}%)  {row['point_count']} pts")
    print()
    print(f"snapping at {SNAP_TOLERANCE_MM:.0f} mm: {report['moved_in']} pulled in, "
          f"{report['moved_out']} pushed out, {report['untouched']} untouched")
    print(f"  spread past the faces: {np.std(offsets_before):.2f} mm before, "
          f"{np.std(offsets_after):.2f} mm after")

    draw(pathlib.Path(run_directory).name, scale, fit, horizontal, vertical_x, vertical_y,
         corners, offsets_before, offsets_after, output_path)


if __name__ == "__main__":
    main()
