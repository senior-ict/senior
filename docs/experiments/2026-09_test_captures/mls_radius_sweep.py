"""Sweep the MLS neighbourhood radius and see what it does to girth and volume.

Starts from Stage 3's pre-MLS dense cluster (03_clean/debug/leg_cluster.ply),
runs the same ghost chain the pipeline runs -- voxel dedup, normal-aware
filter, MLS -- with only the MLS radius varied, and for each radius reports:

  * girth at every taped height against the tape (the model's own error)
  * how bimodal the surface shell is (does the radius merge the double sheet?)
  * the volume between the two cut planes after re-wrapping, by Poisson where
    it closes and by the alpha ladder otherwise (the wrap's error)

The can is the control: it reads +0.9% girth today, and any radius that moves
it is over-smoothing rather than fixing anything.

    python docs/experiments/2026-09_test_captures/mls_radius_sweep.py
"""
import json
import math
import pathlib
import sys

import numpy as np
import open3d as o3d
import trimesh

PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parents[3])
sys.path.insert(0, PROJECT_ROOT)
from pipeline.core.crosssection import fit_slice
from pipeline.core.meshcut import apply_marker_cut_to_mesh
from pipeline.ghost import ghost_voxel_downsample, mls_project, normal_aware_filter
from pipeline.stages.clean import _ghost_filter_scales, _load_and_thin
from pipeline.workers.meshfix_worker import _pymeshfix_repair

# Each entry is a sequence of MLS passes applied in order. A single value is
# the pipeline's one pass at that radius; a pair is the stacked variant -- the
# pipeline's 4x first, to denoise each sheet, then a wide pass to merge them.
RADIUS_MULTIPLIERS = [
    (0.0,), (4.0,), (8.0,), (12.0,), (16.0,), (24.0,), (32.0,),
    (4.0, 12.0), (4.0, 16.0), (4.0, 24.0),
]
ALPHA_LADDER = [8, 10, 12, 14, 16, 20, 25, 30, 40, 50]

CAPTURES = {
    "output_test6": {
        "tape_heights": [0, 1.5, 3.5, 5.5, 7.5, 9.5, 11.5, 13.5, 15.5,
                         17.5, 19.5, 21.5, 23.5, 25.5, 27.5],
        "tape_girths": [19, 19, 19, 20, 21, 22.5, 24.5, 26, 27.5,
                        29, 29.5, 29.5, 29, 28, 28],
        "truth_volume": 1398.6,          # disc model on the taped profile
    },
    "output_fanta_orange": {
        "tape_heights": None,            # measured at fractions of the height
        "tape_girths": [18.5],
        "truth_volume": None,
    },
}


def load_capture(run_name):
    """Pre-MLS cluster, the scene's filter scales, scale in cm, and cut planes."""
    debug = f"{PROJECT_ROOT}/{run_name}/for_debug"
    cluster = o3d.io.read_point_cloud(f"{debug}/03_clean/debug/leg_cluster.ply")
    dense = _load_and_thin(f"{debug}/02_pointcloud/points.ply")
    voxel_size, normal_scale = _ghost_filter_scales(dense)

    levelling = json.load(open(f"{debug}/03_clean/debug/levelling.json"))
    rotation = np.array(levelling["R_total"])
    box = trimesh.load(f"{debug}/05_watertight/mesh/box.ply", process=False)
    scale_cm = (1000.0 / box.volume) ** (1.0 / 3.0)
    cube_volume_units = box.volume

    # A run made with --no-segment-leg publishes no planes; the whole object is
    # then the measurement, so an empty list is the right answer here.
    planes_path = pathlib.Path(f"{debug}/03_clean/debug/cutting_line_levelled.json")
    planes = []
    if planes_path.exists():
        planes = json.load(open(planes_path))["markers"]
        planes = sorted(planes, key=lambda plane: plane["centroid"][2])
    return cluster, voxel_size, normal_scale, rotation, scale_cm, cube_volume_units, planes


def clean_with_radius(cluster, voxel_size, normal_scale, radius_passes):
    """The pipeline's ghost chain, with the MLS passes as the only free choice.

    `radius_passes` is a sequence of radius multipliers applied one after
    another; a single-element sequence is the pipeline's own one-pass MLS.
    """
    points = np.asarray(cluster.points, dtype=np.float32)
    if cluster.has_colors():
        colours = (np.clip(np.asarray(cluster.colors, dtype=np.float32), 0, 1)
                   * 255).astype(np.uint8)
    else:
        # The debug cluster is written without colour. The chain only carries
        # colour alongside geometry, never reads it, so a placeholder is safe.
        colours = np.zeros((len(points), 3), dtype=np.uint8)
    points, colours = ghost_voxel_downsample(points, colours, voxel_size)
    points, colours = normal_aware_filter(points, colours, normal_scale)
    for radius_mult in radius_passes:
        if radius_mult > 0:
            points, colours, _ = mls_project(points, colours, radius_mult=radius_mult,
                                             polynomial=True, verbose=False)
    return np.asarray(points, dtype=np.float64)


def shell_skew(points, height, scale_cm):
    """Skew of radial offsets in one slab: negative means an inward second sheet."""
    slab = points[np.abs(points[:, 2] - height) <= 0.4 / scale_cm]
    if len(slab) < 20:
        return float("nan")
    radial = np.linalg.norm(slab[:, :2] - slab[:, :2].mean(axis=0), axis=1)
    offsets = radial - np.median(radial)
    spread = offsets.std()
    if spread == 0:
        return 0.0
    return float(((offsets - offsets.mean()) ** 3).mean() / spread ** 3)


def girth_errors(points, capture, lower_z, upper_z, scale_cm):
    """Mean percentage girth error against the tape, and the mean shell skew."""
    settings = CAPTURES[capture]
    vertical = np.array([0.0, 0.0, 1.0])
    if settings["tape_heights"] is None:
        # The can: one girth everywhere, sampled at fractions of its height.
        low, high = points[:, 2].min(), points[:, 2].max()
        heights_units = [low + (high - low) * fraction
                         for fraction in (0.3, 0.45, 0.6, 0.75)]
        tape_girths = settings["tape_girths"] * len(heights_units)
    else:
        heights_units = [lower_z + tape_height / scale_cm
                         for tape_height in settings["tape_heights"]]
        tape_girths = settings["tape_girths"]

    errors, skews = [], []
    for height, tape_girth in zip(heights_units, tape_girths):
        try:
            fitted = fit_slice(points, np.array([0.0, 0.0, height]), vertical, scale_cm)
        except ValueError:
            continue
        errors.append(100.0 * (fitted["circumference_cm"] - tape_girth) / tape_girth)
        skews.append(shell_skew(points, height, scale_cm))
    return float(np.mean(errors)), float(np.nanmean(skews))


def poisson_solid(points):
    """Poisson surface, repaired; returns (mesh, euler) or (None, None)."""
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.02, max_nn=100))
    cloud.orient_normals_consistent_tangent_plane(15)
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(cloud, depth=9)
    keep = np.asarray(densities) > np.quantile(np.asarray(densities), 0.05)
    mesh.remove_vertices_by_mask(~keep)
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    candidate = trimesh.Trimesh(vertices, faces, process=False)
    if not candidate.is_watertight:
        vertices, faces = _pymeshfix_repair(vertices, faces)
        candidate = trimesh.Trimesh(vertices, faces, process=False)
    if not candidate.is_watertight:
        return None, None
    return candidate, int(candidate.euler_number)


def alpha_solid(points):
    """Smallest alpha on the ladder giving a closed chi=2 solid; (mesh, mult)."""
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    spacing = float(np.mean(cloud.compute_nearest_neighbor_distance()))
    tetra, index_map = o3d.geometry.TetraMesh.create_from_point_cloud(cloud)
    for multiplier in ALPHA_LADDER:
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(
            cloud, multiplier * spacing, tetra, index_map)
        mesh.remove_degenerate_triangles()
        mesh.remove_duplicated_triangles()
        mesh.remove_duplicated_vertices()
        mesh.remove_non_manifold_edges()
        candidate = trimesh.Trimesh(np.asarray(mesh.vertices),
                                    np.asarray(mesh.triangles), process=False)
        if candidate.is_watertight and int(candidate.euler_number) == 2:
            return candidate, multiplier
    return None, None


def span_volume(solid, planes, cube_volume_units):
    """Volume between the two planes, scaled the way Stage 6 scales it."""
    cut, case = apply_marker_cut_to_mesh(solid, planes)
    if case != "case_2_between":
        return float("nan")
    # abs: a Poisson surface can come out inward-facing, which flips the sign of
    # the signed volume without changing its magnitude.
    return abs(cut.volume) * (1000.0 / cube_volume_units)


def whole_volume(solid, cube_volume_units):
    """Whole-object volume, for the can which has no cut planes."""
    return abs(solid.volume) * (1000.0 / cube_volume_units)


def sweep(run_name):
    """Run every radius on one capture and print the table."""
    (cluster, voxel_size, normal_scale, rotation,
     scale_cm, cube_volume_units, planes) = load_capture(run_name)
    settings = CAPTURES[run_name]
    lower_z = planes[0]["centroid"][2] if planes else None
    upper_z = planes[-1]["centroid"][2] if planes else None

    print(f"\n=== {run_name} ===   truth volume "
          f"{settings['truth_volume'] if settings['truth_volume'] else 'n/a'}")
    print(f'{"mls":>5s} {"pts":>6s} {"girth err":>10s} {"skew":>6s} '
          f'{"poisson chi":>11s} {"vol(poisson)":>12s} {"alpha":>6s} {"vol(alpha)":>11s}')
    for radius_passes in RADIUS_MULTIPLIERS:
        pass_label = "→".join(f"{multiplier:.0f}" for multiplier in radius_passes)
        cleaned = clean_with_radius(cluster, voxel_size, normal_scale, radius_passes)
        levelled = cleaned @ rotation.T
        girth_error, skew = girth_errors(levelled, run_name, lower_z, upper_z, scale_cm)

        poisson_mesh, euler = poisson_solid(levelled)
        alpha_mesh, alpha_mult = alpha_solid(levelled)

        def volume_of(solid):
            """Span volume when planes exist, else the whole object; nan if no mesh."""
            if solid is None:
                return float("nan")
            if planes and len(planes) >= 2:
                return span_volume(solid, planes, cube_volume_units)
            return whole_volume(solid, cube_volume_units)

        poisson_volume = volume_of(poisson_mesh) if euler == 2 else float("nan")
        alpha_volume = volume_of(alpha_mesh)
        print(f"{pass_label:>5s} {len(cleaned):6d} {girth_error:+9.1f}% {skew:+6.2f} "
              f"{str(euler) if euler is not None else 'open':>11s} {poisson_volume:12.1f} "
              f"{str(alpha_mult) + 'x' if alpha_mult else 'none':>6s} {alpha_volume:11.1f}")


if __name__ == "__main__":
    # Names on the command line restrict the sweep; none means every capture.
    requested = sys.argv[1:] or list(CAPTURES)
    for capture_name in requested:
        sweep(capture_name)
