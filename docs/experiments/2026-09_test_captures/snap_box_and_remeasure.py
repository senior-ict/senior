"""Snap the reference cube's points onto the cube that fits them, re-mesh, and re-measure the leg.

The cube reconstructs as a correct cube with about 2 mm of fuzz on its faces
and rounded corners (see box_skeleton.py). Stage 6 takes its scale from the
cube MESH's volume, so that fuzz, the skirt Stage 3 adds under the cube, and
the holes Poisson leaves all land in the scale.

This moves every cube point that sits more than a tolerance from its nearest
ideal face onto that face, meshes the result with the pipeline's own Stage 4
and Stage 5, and reports what the new scale does to the limb volume. The limb
mesh is untouched, so any change is the reference's doing alone.

    python snap_box_and_remeasure.py <run dir> <scratch dir> <truth cm3> [tolerance mm ...]
"""
import pathlib
import sys

import numpy as np
import open3d as o3d
import trimesh

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.cube_fit import distance_to_cube_surface, fit_cube  # noqa: E402
from pipeline.stages.reconstruct import reconstruct_multiple_objects  # noqa: E402
from pipeline.stages.watertight import make_watertight_meshes  # noqa: E402

REFERENCE_VOLUME_CM3 = 1000.0
REFERENCE_SIDE_CM = 10.0


def cube_frame_axes(fit):
    """The cube's own three unit axes, as the rows of a rotation matrix."""
    yaw = np.radians(fit["yaw_degrees"])
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    return np.array([[cosine, -sine, 0.0],
                     [sine, cosine, 0.0],
                     [0.0, 0.0, 1.0]])


def snap_points_to_cube(points, fit, tolerance_units):
    """Move points further than the tolerance from their nearest ideal face onto it."""
    rotation = cube_frame_axes(fit)
    centre = np.array([fit["centre"][0], fit["centre"][1], fit["bottom"] + fit["side"] / 2.0])
    local = (points - centre) @ rotation.T
    half_side = fit["side"] / 2.0

    nearest_axis = np.argmax(np.abs(local), axis=1)
    row_index = np.arange(len(local))
    offsets = np.abs(local[row_index, nearest_axis]) - half_side
    moving = np.abs(offsets) > tolerance_units

    moved_local = local.copy()
    targets = np.sign(local[row_index, nearest_axis]) * half_side
    moving_rows = np.flatnonzero(moving)
    moved_local[moving_rows, nearest_axis[moving_rows]] = targets[moving_rows]

    moved_points = moved_local @ rotation + centre
    report = {"pulled_in": int(np.sum(moving & (offsets > 0))),
              "pushed_out": int(np.sum(moving & (offsets < 0))),
              "untouched": int(np.sum(~moving))}
    return moved_points, report


def mesh_the_cloud(points, colours, work_directory):
    """Run Stage 4 and Stage 5 on one cloud and return its watertight mesh."""
    work_directory.mkdir(parents=True, exist_ok=True)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points)
    if colours is not None and len(colours) == len(points):
        cloud.colors = o3d.utility.Vector3dVector(colours)
    cloud_path = work_directory / "box.ply"
    o3d.io.write_point_cloud(str(cloud_path), cloud)

    _, _, recon_paths = reconstruct_multiple_objects([str(cloud_path)],
                                                     output_folder=str(work_directory / "recon"),
                                                     base_name="scene_recon")
    _, _, watertight_paths = make_watertight_meshes(recon_paths,
                                                    output_folder=str(work_directory / "watertight"),
                                                    base_name="scene")
    return trimesh.load(watertight_paths[0], process=False)


def report_scale(label, box_mesh, limb_units, fitted_side_units, truth_cm3):
    """Print what one reference mesh does to the scale and to the limb volume."""
    box_volume_units = abs(box_mesh.volume)
    scale = (REFERENCE_VOLUME_CM3 / box_volume_units) ** (1.0 / 3.0)
    limb_volume = limb_units * scale ** 3
    print(f"  {label:<26}{box_volume_units:>12.8f}{scale:>12.3f}"
          f"{fitted_side_units * scale:>12.3f}{limb_volume:>12.1f}"
          f"{100 * (limb_volume / truth_cm3 - 1):>9.1f}%")
    return scale, limb_volume


def main():
    """Snap at each tolerance, re-mesh, and compare the limb volume each one implies."""
    run = pathlib.Path(sys.argv[1])
    scratch = pathlib.Path(sys.argv[2])
    truth_cm3 = float(sys.argv[3])
    tolerances_mm = [float(value) for value in sys.argv[4:]] or [2.0]

    cloud = o3d.io.read_point_cloud(str(run / "for_debug/03_clean/objects/box.ply"))
    points = np.asarray(cloud.points)
    colours = np.asarray(cloud.colors) if cloud.has_colors() else None
    original_box = trimesh.load(str(run / "for_debug/05_watertight/mesh/box.ply"), process=False)
    limb = trimesh.load(str(run / "for_debug/05_watertight/mesh/leg_cut.ply"), process=False)
    limb_units = abs(limb.volume)

    fit = fit_cube(points)
    original_scale = (REFERENCE_VOLUME_CM3 / abs(original_box.volume)) ** (1.0 / 3.0)
    print(f"as it stands: fitted side {fit['side'] * original_scale:.3f} cm, "
          f"residual {fit['residual'] * original_scale * 10:.2f} mm")
    print()
    print(f"  {'reference mesh':<26}{'box units3':>12}{'cm/unit':>12}{'fitted cm':>12}"
          f"{'limb cm3':>12}{'vs tape':>10}")
    report_scale("as reconstructed", original_box, limb_units, fit["side"], truth_cm3)

    for tolerance_mm in tolerances_mm:
        tolerance_units = (tolerance_mm / 10.0) / original_scale
        snapped, snap_report = snap_points_to_cube(points, fit, tolerance_units)
        work_directory = scratch / f"snap_{tolerance_mm:g}mm"
        snapped_mesh = mesh_the_cloud(snapped, colours, work_directory)
        distances = distance_to_cube_surface(snapped, np.radians(fit["yaw_degrees"]),
                                             fit["centre"][0], fit["centre"][1],
                                             fit["bottom"], fit["side"])
        print(f"  snapped at {tolerance_mm:g} mm: {snap_report['pulled_in']} in, "
              f"{snap_report['pushed_out']} out, {snap_report['untouched']} untouched, "
              f"residual now {np.sqrt(np.mean(distances ** 2)) * original_scale * 10:.2f} mm, "
              f"watertight {snapped_mesh.is_watertight}")
        report_scale(f"snapped at {tolerance_mm:g} mm", snapped_mesh, limb_units, fit["side"], truth_cm3)

    ideal_volume_units = fit["side"] ** 3
    print(f"  {'the fitted cube itself':<26}{ideal_volume_units:>12.8f}"
          f"{REFERENCE_SIDE_CM / fit['side']:>12.3f}{REFERENCE_SIDE_CM:>12.3f}"
          f"{limb_units * (REFERENCE_SIDE_CM / fit['side']) ** 3:>12.1f}"
          f"{100 * (limb_units * (REFERENCE_SIDE_CM / fit['side']) ** 3 / truth_cm3 - 1):>9.1f}%")
    print()
    print(f"truth {truth_cm3:.1f} cm3; the limb mesh is the same in every row "
          f"({limb_units:.8f} units3), only the reference changes.")


if __name__ == "__main__":
    main()
