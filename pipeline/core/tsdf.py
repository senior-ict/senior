"""Fuse VGGT's per-frame depth maps into one surface with a truncated signed
distance volume.

Stage 2's default cloud stacks the eight per-view pointmaps on top of each
other. Each view places the skin a little differently and every placement is
kept, which is where the ghost double sheet comes from: two skins about a
centimetre apart that Stage 3's ghost voxel, normal filter and two MLS passes
exist to collapse. Fusing the depth maps instead settles the disagreement
before Stage 3 sees the cloud. Every frame's depth votes for the cells along
its rays, the votes are averaged, and the surface is where the averaged
signed distance crosses zero. One skin, by construction.

Measured on inputs/test6 (2026-09-19, docs/experiments/2026-09_test_captures/
TSDF_STAGE2.md): the reference cube fills 0.87 of its oriented box instead of
0.73, Poisson closes on both objects with no MLS merge and no alpha
fallback, and the girth profile drops from +7.3% to +5.8% against the tape.
The volume between the bands does not move (1704 -> 1686 cm3), because a
bias shared by every view averages to the same bias. This is a cleaner
surface, not a correction.

The voxel is sized in centimetres, so a scale is needed before Stage 6 has
one. The ArUco markers give it: their 5 cm edges in the raw point map
(pipeline/core/marker_scale.py) need no mesh. When no marker is found the
voxel falls back to a fixed size in scene units.
"""
import numpy as np

from pipeline.config import (TSDF_FAR_DEPTH_MULT, TSDF_FALLBACK_VOXEL_UNITS,
                             TSDF_TRUNCATION_VOXELS, TSDF_VOXEL_CM)

# The same percentile cut Stage 2's pointmap path applies, so both paths keep
# the same pixels and differ only in how they are combined.
CONFIDENCE_PERCENTILE = 45.0
# A fused point survives only if the filtered pointmap cloud has a point
# within this many voxels of it (see keep_supported).
SUPPORT_VOXELS = 3.0


def voxel_size_in_units(predictions, voxel_cm=TSDF_VOXEL_CM, verbose=True):
    """The voxel edge in scene units, from the markers' scale when they are visible."""

    marker = marker_scale_from_predictions_safe(predictions)
    if marker is None:
        if verbose:
            print(f"  TSDF: no ArUco marker found on any frame — voxel fixed at "
                  f"{TSDF_FALLBACK_VOXEL_UNITS} scene units")
        return TSDF_FALLBACK_VOXEL_UNITS
    voxel_units = voxel_cm / marker["cm_per_unit"]
    if verbose:
        print(f"  TSDF: markers give {marker['cm_per_unit']:.2f} cm/unit "
              f"({marker['edge_count']} edges on {marker['frames_with_markers']} frames); "
              f"voxel {voxel_cm} cm = {voxel_units:.5f} units")
    return voxel_units


def marker_scale_from_predictions_safe(predictions):
    """The marker scale from an in-memory predictions dict, or None.

    `marker_scale_from_predictions` reads a file; Stage 2 in run.py holds the
    arrays already, so the same computation is done on the dict here.
    """
    from pipeline.core.marker_scale import detect_marker_corners, marker_edge_lengths
    from pipeline.config import REFERENCE_MARKER_CM

    images = np.asarray(predictions["images"]).transpose(0, 2, 3, 1)
    world_points = np.asarray(predictions["world_points"])
    confidence = np.asarray(predictions["world_points_conf"])
    all_lengths = []
    frames_with_markers = 0
    for frame_index, image in enumerate(images):
        corners_per_marker = detect_marker_corners(image)
        if corners_per_marker:
            frames_with_markers += 1
        for corners in corners_per_marker:
            all_lengths.extend(marker_edge_lengths(
                world_points[frame_index], confidence[frame_index], corners))
    if not all_lengths:
        return None
    return {"cm_per_unit": REFERENCE_MARKER_CM / float(np.median(all_lengths)),
            "edge_count": len(all_lengths),
            "frames_with_markers": frames_with_markers}


def fuse_depth_maps(predictions, voxel_units, support_points=None, verbose=True):
    """Integrate every frame's depth map into one TSDF and return (points, colours uint8).

    Pixels below the confidence cut in either head are not integrated, and
    nothing farther than TSDF_FAR_DEPTH_MULT times the confident pointmap's
    95th-percentile depth is either: without that cut the fusion also builds
    the far walls and ceiling, which the pointmap path never keeps, and
    Stage 3's clustering then merges the limb into the room.
    """
    import open3d as o3d

    depth_maps = np.asarray(predictions["depth"])
    if depth_maps.ndim == 4:
        depth_maps = depth_maps[..., 0]
    depth_maps = depth_maps.astype(np.float32)
    depth_confidence = np.asarray(predictions["depth_conf"])
    pointmap_confidence = np.asarray(predictions["world_points_conf"])
    intrinsics = np.asarray(predictions["intrinsic"])
    extrinsics = np.asarray(predictions["extrinsic"])
    images = np.asarray(predictions["images"]).transpose(0, 2, 3, 1)
    frame_count, height, width = depth_maps.shape

    # The same adaptive threshold Stage 2's pointmap path uses, not a raw
    # percentile: on these captures most pixels sit at the minimum confidence
    # and the adaptive rule raises the bar well above the percentile.
    from pipeline.core.filters import adaptive_confidence_filter

    depth_floor = adaptive_confidence_filter(depth_confidence.reshape(-1), CONFIDENCE_PERCENTILE)
    pointmap_floor = adaptive_confidence_filter(pointmap_confidence.reshape(-1), CONFIDENCE_PERCENTILE)
    confident_depths = depth_maps[pointmap_confidence >= pointmap_floor]
    far_depth = float(np.percentile(confident_depths, 95)) * TSDF_FAR_DEPTH_MULT

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=float(voxel_units),
        sdf_trunc=float(TSDF_TRUNCATION_VOXELS * voxel_units),
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for frame_index in range(frame_count):
        depth = np.ascontiguousarray(depth_maps[frame_index].copy())
        depth[depth_confidence[frame_index] < depth_floor] = 0.0
        depth[pointmap_confidence[frame_index] < pointmap_floor] = 0.0
        depth[depth > far_depth] = 0.0
        colour = np.ascontiguousarray((np.clip(images[frame_index], 0, 1) * 255).astype(np.uint8))
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(colour), o3d.geometry.Image(depth),
            depth_scale=1.0, depth_trunc=float(far_depth), convert_rgb_to_intensity=False)
        camera = o3d.camera.PinholeCameraIntrinsic(
            width, height,
            float(intrinsics[frame_index, 0, 0]), float(intrinsics[frame_index, 1, 1]),
            float(intrinsics[frame_index, 0, 2]), float(intrinsics[frame_index, 1, 2]))
        world_to_camera = np.eye(4)
        world_to_camera[:3] = extrinsics[frame_index]
        volume.integrate(rgbd, camera, world_to_camera)

    cloud = volume.extract_point_cloud()
    points = np.asarray(cloud.points, dtype=np.float32)
    fused_count = len(points)
    if support_points is not None:
        points = keep_supported(points, support_points, voxel_units)
    colours = recolour_from_pointmap(points, predictions, pointmap_floor)
    if verbose:
        print(f"  TSDF: fused {frame_count} depth maps at voxel {voxel_units:.5f} units, "
              f"depth cut {far_depth:.3f} units -> {fused_count:,} surface points"
              + (f", {len(points):,} with support in the filtered pointmap cloud"
                 if support_points is not None else ""))
    return points, colours


def keep_supported(points, support_points, voxel_units):
    """Only the fused points that lie within a few voxels of a supporting point.

    The pointmap path's outlier removal deletes far surfaces because they are
    sparse; a TSDF densifies those same surfaces onto a regular grid, so
    nothing deletes them and Stage 3 clusters the walls and the far floor.
    Requiring a point of the filtered pointmap cloud within SUPPORT_VOXELS of
    every fused point keeps the two paths describing the same scene.
    """
    from scipy.spatial import cKDTree

    distance, _ = cKDTree(support_points).query(points, k=1, workers=-1)
    return points[distance <= SUPPORT_VOXELS * voxel_units]


def recolour_from_pointmap(points, predictions, pointmap_floor):
    """Colour of the nearest confident pointmap point, for every fused point, as uint8.

    The TSDF averages colour across views, which blurs a thin marker cord into
    the skin around it until Stage 3's colour rule cannot find it. The
    pointmap's own per-point colours keep the cord, so they are copied back.
    """
    from scipy.spatial import cKDTree

    world_points = np.asarray(predictions["world_points"]).reshape(-1, 3)
    confidence = np.asarray(predictions["world_points_conf"]).reshape(-1)
    colours = np.asarray(predictions["images"]).transpose(0, 2, 3, 1).reshape(-1, 3)
    keep = (confidence >= pointmap_floor) & (confidence > 1e-5)
    tree = cKDTree(world_points[keep])
    _, nearest = tree.query(points, k=1, workers=-1)
    return (np.clip(colours[keep][nearest], 0, 1) * 255.0).astype(np.uint8)
