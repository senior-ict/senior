"""Compare the scale three ways on a finished run: fitted cube, mesh volume, printed markers.

The fit itself is pipeline/core/cube_fit.py, which Stage 6 also uses as its
reference check; this script only runs it over several runs and draws it.

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

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.cube_fit import distance_to_cube_surface, fit_cube  # noqa: E402
from pipeline.core.marker_scale import marker_scale_from_predictions  # noqa: E402

REFERENCE_SIDE_CM = 10.0

def fit_run_cube(points):
    """Fit the cube and add the point set the figure draws."""
    fit = fit_cube(points)
    if fit is None:
        raise SystemExit("too few reference points to fit a cube")
    distances = distance_to_cube_surface(points, np.radians(fit["yaw_degrees"]), fit["centre"][0],
                                         fit["centre"][1], fit["bottom"], fit["side"])
    spread = 1.4826 * np.median(np.abs(distances - np.median(distances)))
    fit["points"] = points
    fit["inliers"] = distances <= np.median(distances) + 3.0 * max(spread, 1e-9)
    return fit


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
    side_view.set_title(f"from the side — residual {fit['residual'] * scale_cm * 10:.2f} mm", fontsize=11)
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
        points, mesh, _, predictions_path = load_run(run_directory)
        fit = fit_run_cube(points)

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
