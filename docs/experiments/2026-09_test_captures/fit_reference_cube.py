"""Fit an ideal cube to the reference cube's points, and compare the scale it implies.

Stage 6 takes its scale from the reference cube's MESH volume: the mesh is
declared to be 1000 cm3, so the scale is the cube root of a volume. That cube
root is exactly what a loose alpha wrap corrupts (the can capture, 2026-09-23:
the cube filled 0.781 of its own box and Poisson could not close it at all).

This fits the shape we know instead. After Stage 3's levelling the cube stands
on the floor, so an ideal cube has four unknowns: its side, its yaw about the
vertical, and where its centre sits. The fit minimises each point's distance to
that cube's surface, and reports the residual, which is the check: a cube that
did not reconstruct as a cube cannot have a small one.

Nothing in the pipeline is changed. This prints, per run, the side length three
ways -- fitted, from the mesh volume, and from the 5 cm printed markers -- and
what each would do to the limb's volume.

    python docs/experiments/2026-09_test_captures/fit_reference_cube.py <run dir> [run dir ...]
    python .../fit_reference_cube.py --figure cube_fit.png <run dir>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import open3d as o3d
import trimesh
from scipy.optimize import minimize

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.marker_scale import marker_scale_from_predictions  # noqa: E402

REFERENCE_SIDE_CM = 10.0
REFERENCE_VOLUME_CM3 = REFERENCE_SIDE_CM ** 3
FABRICATED_BASE_CM = 1.0          # Stage 3 invents points here to close the base
YAW_STEP_DEGREES = 1.0            # a cube repeats every quarter turn
POLISH_COUNT = 5                  # how many of the best sweep angles to refine
OUTLIER_ROUNDS = 3
OUTLIER_SPREAD_MULTIPLE = 3.0


def load_run(run_directory):
    """Cube points (levelled), the cube mesh, the floor height, and the predictions path."""
    run = pathlib.Path(run_directory)
    stage_root = run / "for_debug" if (run / "for_debug").is_dir() else run
    points = np.asarray(o3d.io.read_point_cloud(str(stage_root / "03_clean/objects/box.ply")).points)
    mesh = trimesh.load(str(stage_root / "05_watertight/mesh/box.ply"), process=False)
    floor_height = json.load(open(stage_root / "03_clean/debug/levelling.json"))["floor_z"]
    predictions = stage_root / "01_inference/predictions.npz"
    return points, mesh, floor_height, predictions


def distance_to_cube_surface(points, yaw, centre_x, centre_y, bottom, side):
    """Each point's distance to the surface of an upright cube of this side, yaw and centre."""
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    local_x = (points[:, 0] - centre_x) * cosine - (points[:, 1] - centre_y) * sine
    local_y = (points[:, 0] - centre_x) * sine + (points[:, 1] - centre_y) * cosine
    local_z = points[:, 2] - (bottom + side / 2.0)
    half = side / 2.0
    offsets = np.abs(np.column_stack([local_x, local_y, local_z])) - half
    outside = np.linalg.norm(np.maximum(offsets, 0.0), axis=1)
    inside = np.minimum(offsets.max(axis=1), 0.0)
    return np.abs(outside + inside)


def fit_at_yaw(points, yaw, start_bottom, start_side, start_centre):
    """Best centre, base height and side for a fixed yaw; returns (cost, parameters)."""
    def cost(parameters):
        """Mean squared distance from the points to the cube these parameters describe."""
        centre_x, centre_y, bottom, side = parameters
        if side <= 0:
            return 1e6
        return float(np.mean(distance_to_cube_surface(points, yaw, centre_x, centre_y, bottom, side) ** 2))

    result = minimize(cost, [start_centre[0], start_centre[1], start_bottom, start_side],
                      method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-10, "maxiter": 3000})
    return float(result.fun), result.x


def fit_cube(points, floor_height):
    """Fit an ideal upright cube to the points. Returns a dictionary of the fit and its quality."""
    # Stage 3 fabricates the base to close the cube, and where the floor was
    # never detected (the can capture) there is no floor height to stand on, so
    # the base height is fitted like everything else.
    kept = points[points[:, 2] > points[:, 2].min()]
    start_bottom = float(floor_height) if floor_height is not None else float(np.percentile(kept[:, 2], 1))
    start_side = float(np.percentile(kept[:, 2], 99) - start_bottom)
    start_centre = kept[:, :2].mean(axis=0)

    working = kept
    best = None
    for _ in range(OUTLIER_ROUNDS):
        sweep = []
        for yaw_degrees in np.arange(0.0, 90.0, YAW_STEP_DEGREES):
            yaw = np.radians(yaw_degrees)
            cost, parameters = fit_at_yaw(working, yaw, start_bottom, start_side, start_centre)
            sweep.append((cost, yaw, parameters))
        sweep.sort(key=lambda entry: entry[0])

        best = None
        for cost, yaw, parameters in sweep[:POLISH_COUNT]:
            def full_cost(values):
                """Mean squared distance with the yaw free as well."""
                yaw_value, centre_x, centre_y, bottom_value, side = values
                if side <= 0:
                    return 1e6
                return float(np.mean(
                    distance_to_cube_surface(working, yaw_value, centre_x, centre_y, bottom_value, side) ** 2))

            polished = minimize(full_cost, [yaw, parameters[0], parameters[1], parameters[2], parameters[3]],
                                method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-12, "maxiter": 6000})
            if best is None or polished.fun < best.fun:
                best = polished

        yaw, centre_x, centre_y, bottom, side = best.x
        distances = distance_to_cube_surface(kept, yaw, centre_x, centre_y, bottom, side)
        spread = 1.4826 * np.median(np.abs(distances - np.median(distances)))
        working = kept[distances <= np.median(distances) + OUTLIER_SPREAD_MULTIPLE * max(spread, 1e-9)]
        start_side, start_centre, start_bottom = side, (centre_x, centre_y), bottom

    yaw, centre_x, centre_y, bottom, side = best.x
    distances = distance_to_cube_surface(kept, yaw, centre_x, centre_y, bottom, side)
    inliers = distances <= np.median(distances) + OUTLIER_SPREAD_MULTIPLE * (
        1.4826 * np.median(np.abs(distances - np.median(distances))))
    return {"side": float(side), "yaw_degrees": float(np.degrees(yaw) % 90.0),
            "centre": (float(centre_x), float(centre_y)), "bottom": float(bottom),
            "residual_units": float(np.sqrt(np.mean(distances[inliers] ** 2))),
            "inlier_fraction": float(inliers.mean()), "points": kept, "inliers": inliers}


def ideal_cube_faces(fit):
    """The six faces of the fitted cube, each as four corner points in scene units."""
    yaw = np.radians(fit["yaw_degrees"])
    half = fit["side"] / 2.0
    centre = np.array([fit["centre"][0], fit["centre"][1], fit["bottom"] + half])
    corners = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype=float) * half
    rotation = np.array([[np.cos(yaw), -np.sin(yaw), 0.0],
                         [np.sin(yaw), np.cos(yaw), 0.0],
                         [0.0, 0.0, 1.0]])
    placed = corners @ rotation.T + centre
    face_indices = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                    (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]
    return [placed[list(indices)] for indices in face_indices]


def draw_figure(fit, points, output_path, scale_cm, title):
    """Three views: the points in 3-D inside the fitted cube, from above, and from the side."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    centre_x, centre_y = fit["centre"]
    side_cm = fit["side"] * scale_cm
    inliers = fit["inliers"]
    centred = np.column_stack([(points[:, 0] - centre_x) * scale_cm,
                               (points[:, 1] - centre_y) * scale_cm,
                               (points[:, 2] - fit["bottom"]) * scale_cm])

    figure = plt.figure(figsize=(14, 5.2), facecolor="#fcfcfb")
    space = figure.add_subplot(1, 3, 1, projection="3d")
    space.set_facecolor("#fcfcfb")
    faces = []
    for face in ideal_cube_faces(fit):
        faces.append(np.column_stack([(face[:, 0] - centre_x) * scale_cm,
                                      (face[:, 1] - centre_y) * scale_cm,
                                      (face[:, 2] - fit["bottom"]) * scale_cm]))
    space.add_collection3d(Poly3DCollection(faces, facecolors=(0.70, 0.15, 0.12, 0.13),
                                            edgecolors="#b3261e", linewidths=1.4))
    space.scatter(centred[inliers, 0], centred[inliers, 1], centred[inliers, 2], s=1.5,
                  color="#2f3a44", depthshade=False)
    space.scatter(centred[~inliers, 0], centred[~inliers, 1], centred[~inliers, 2], s=3,
                  color="#e08a1e", depthshade=False)
    limit = side_cm * 0.85
    space.set_xlim(-limit, limit)
    space.set_ylim(-limit, limit)
    space.set_zlim(-1, 2 * limit - 1)
    space.set_box_aspect((1, 1, 1))
    space.view_init(elev=16, azim=-58)
    space.set_axis_off()
    space.set_title("points and the fitted 10 cm cube", fontsize=11)

    top = figure.add_subplot(1, 3, 2)
    outline = ideal_cube_faces(fit)[1]
    outline_cm = np.column_stack([(outline[:, 0] - centre_x) * scale_cm,
                                  (outline[:, 1] - centre_y) * scale_cm])
    closed = np.vstack([outline_cm, outline_cm[:1]])
    top.scatter(centred[inliers, 0], centred[inliers, 1], s=2, color="#2f3a44")
    top.scatter(centred[~inliers, 0], centred[~inliers, 1], s=4, color="#e08a1e")
    top.plot(closed[:, 0], closed[:, 1], color="#b3261e", linewidth=2)
    top.set_aspect("equal")
    top.set_xlabel("cm")
    top.set_title(f"from above — side {side_cm:.2f} cm, yaw {fit['yaw_degrees']:.1f}°", fontsize=11)
    top.grid(alpha=0.25)

    side_view = figure.add_subplot(1, 3, 3)
    side_view.scatter(centred[inliers, 0], centred[inliers, 2], s=2, color="#2f3a44")
    side_view.scatter(centred[~inliers, 0], centred[~inliers, 2], s=4, color="#e08a1e")
    for height in (0.0, side_cm):
        side_view.axhline(height, color="#b3261e", linewidth=2)
    side_view.axvline(-side_cm / 2, color="#b3261e", linewidth=1, linestyle=(0, (4, 3)))
    side_view.axvline(side_cm / 2, color="#b3261e", linewidth=1, linestyle=(0, (4, 3)))
    side_view.set_aspect("equal")
    side_view.set_xlabel("cm")
    side_view.set_ylabel("height above the cube's base (cm)")
    side_view.set_title(f"from the side — residual {fit['residual_units'] * scale_cm * 10:.2f} mm", fontsize=11)
    side_view.grid(alpha=0.25)

    figure.suptitle(f"{title}: dark = points the fit kept, orange = points it set aside", fontsize=12)
    figure.tight_layout(rect=[0, 0, 1, 0.94])
    figure.savefig(output_path, dpi=110, facecolor="#fcfcfb")
    plt.close(figure)
    print(f"  figure: {output_path}")


def main():
    """Fit the cube in each run and print the three scales side by side."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--figure", default=None, help="write a picture of the first run's fit here")
    arguments = parser.parse_args()

    print(f"{'run':<22}{'fitted side':>13}{'mesh side':>11}{'marker side':>13}"
          f"{'residual':>10}{'inliers':>9}{'yaw':>7}{'limb change':>13}")
    for index, run_directory in enumerate(arguments.runs):
        points, mesh, floor_height, predictions_path = load_run(run_directory)
        fit = fit_cube(points, floor_height)

        mesh_side = abs(mesh.volume) ** (1.0 / 3.0)
        fitted_scale_cm = REFERENCE_SIDE_CM / fit["side"]
        mesh_scale_cm = REFERENCE_SIDE_CM / mesh_side
        marker = marker_scale_from_predictions(str(predictions_path))
        marker_scale_cm = marker["cm_per_unit"] if marker else float("nan")
        marker_side = REFERENCE_SIDE_CM / marker_scale_cm if marker else float("nan")
        volume_change = 100 * ((fitted_scale_cm / mesh_scale_cm) ** 3 - 1)

        name = pathlib.Path(run_directory).name
        print(f"{name:<22}{fit['side'] * mesh_scale_cm:>12.2f}c{mesh_side * mesh_scale_cm:>10.2f}c"
              f"{marker_side * mesh_scale_cm:>12.2f}c{fit['residual_units'] * mesh_scale_cm * 10:>8.2f}mm"
              f"{100 * fit['inlier_fraction']:>8.0f}%{fit['yaw_degrees']:>6.1f}°{volume_change:>12.1f}%")

        if arguments.figure:
            figure_path = arguments.figure
            if len(arguments.runs) > 1:
                figure_path = figure_path.replace(".png", f"_{name}.png")
            draw_figure(fit, fit["points"], figure_path, mesh_scale_cm, name)


if __name__ == "__main__":
    main()
