"""The reference cube's own 3D points, from Stage 0's ArUco boxes.

Stage 3 has to decide which of its two clusters is the reference cube, because
every centimetre the pipeline reports comes from that object's known 10 cm
side. Until now it decided by a shape-and-colour score: how cube-like a
cluster's bounding box is, plus how much of it is near-black or near-white.
Both are properties a leg can have. On `inputs/4_circumference_calculation_2c_hairless` the leg
won, the run scaled every measurement off a thigh, and nothing in the output
said so.

The information needed to settle it already exists and is simply in the wrong
space. Stage 0 detects ArUco markers on the cube's faces and records the box
they occupy in frame pixels, per photograph. Stage 1's `world_points` holds a
3D position for every pixel of every frame. Mapping one through the other turns
"the markers were here in this photograph" into thousands of 3D points sitting
on the real cube -- which is evidence, not a resemblance.

This is the same trick `bands3d.py` plays for the cut planes, and it reuses
that module's pixel mapping so the two cannot disagree about where a frame's
pixels ended up.

What this does NOT do is reconstruct or measure the cube. It only produces a
set of points that are known to be on it, dense enough to vote with.
"""
import json
import os

import numpy as np

from pipeline.core.bands3d import _frame_to_input_box

# Keep only the middle of each cube box. The recorded box is the union of the
# recovered marker faces, padded, so its outer rim is background and floor
# rather than cube. 0.7 keeps most of the cube's own pixels while staying
# clear of the rim; the vote only needs points that are certainly on the cube,
# not every point that might be.
BOX_CORE_FRAC = 0.7

# Confidence percentile, within each frame, below which a pixel's 3D position
# is not used. Same reasoning as bands3d: VGGT reports low confidence on the
# surfaces it reconstructs badly, and those points land anywhere.
CONFIDENCE_PERCENTILE = 60.0


def _cube_pixels(record, cube_box, input_size, preprocess):
    """Pixel bounds of one frame's cube box inside the array VGGT consumed.

    Returns (left, top, right, bottom) in the 518-pixel input frame, or None
    when the frame cannot be mapped or the mapped box is too small to sample.
    """
    mapped = _frame_to_input_box(record, input_size, preprocess=preprocess)
    if mapped is None:
        return None
    origin, scale_x, scale_y, offset_y = mapped

    box_left = float(cube_box[0])
    box_top = float(cube_box[1])
    box_right = float(cube_box[2])
    box_bottom = float(cube_box[3])

    # Shrink the box towards its own centre, keeping BOX_CORE_FRAC of each side.
    centre_x = (box_left + box_right) / 2.0
    centre_y = (box_top + box_bottom) / 2.0
    half_width = (box_right - box_left) * BOX_CORE_FRAC / 2.0
    half_height = (box_bottom - box_top) * BOX_CORE_FRAC / 2.0
    box_left, box_right = centre_x - half_width, centre_x + half_width
    box_top, box_bottom = centre_y - half_height, centre_y + half_height

    left = (box_left - origin[0]) * scale_x
    right = (box_right - origin[0]) * scale_x
    top = (box_top - origin[1]) * scale_y - offset_y
    bottom = (box_bottom - origin[1]) * scale_y - offset_y

    left, right = sorted((int(np.floor(left)), int(np.ceil(right))))
    top, bottom = sorted((int(np.floor(top)), int(np.ceil(bottom))))
    left, top = max(0, left), max(0, top)
    right, bottom = min(input_size, right), min(input_size, bottom)
    if right - left < 2 or bottom - top < 2:
        return None
    return left, top, right, bottom


def reference_points_from_arrays(manifest, world_points, world_points_conf,
                                 verbose=True):
    """Points known to sit on the reference cube, in ORIGINAL VGGT space.

    That is the same space Stage 3 clusters in, before levelling, so the result
    can be compared directly against a cluster's points.

    Returns an empty (0, 3) array -- never raises -- whenever the inputs cannot
    be related: a run with no Stage 0, a manifest from before the cube box was
    recorded, a frame count that does not match the pointmap. An empty result
    leaves identification exactly as it was; a wrong one would pick the wrong
    object to scale from.
    """
    empty = np.zeros((0, 3), dtype=np.float64)
    try:
        frames = manifest.get("frames", [])
    except AttributeError:
        return empty
    records = []
    for record in frames:
        if record.get("output"):
            records.append(record)
    if not records:
        return empty

    points = np.asarray(world_points)
    confidence = np.asarray(world_points_conf)
    if points.ndim != 4 or len(points) != len(records):
        if verbose:
            print(f"  cube projection skipped: {len(points)} pointmaps for "
                  f"{len(records)} framed images — they cannot be paired")
        return empty

    input_size = points.shape[1]
    preprocess = manifest.get("vggt_preprocess", "crop")
    collected = []
    frames_with_cube = 0
    for frame_index, record in enumerate(records):
        cube_box = record.get("cube_bbox")
        if not cube_box:
            continue
        frames_with_cube += 1
        bounds = _cube_pixels(record, cube_box, input_size, preprocess)
        if bounds is None:
            continue
        left, top, right, bottom = bounds
        frame_confidence = confidence[frame_index]
        floor = float(np.percentile(frame_confidence, CONFIDENCE_PERCENTILE))
        patch = points[frame_index, top:bottom, left:right].reshape(-1, 3)
        patch_confidence = frame_confidence[top:bottom, left:right].reshape(-1)
        keep = patch_confidence >= floor
        if keep.sum() < 4:
            continue
        collected.append(patch[keep])

    if not collected:
        if verbose and frames_with_cube:
            print("  cube projection: no confident 3D points under any cube box")
        return empty

    coordinates = np.concatenate(collected).astype(np.float64)
    finite = np.isfinite(coordinates).all(axis=1)
    coordinates = coordinates[finite]
    if verbose:
        print(f"  Cube projection: {len(coordinates):,} points on the reference "
              f"from {frames_with_cube} frame(s) of Stage 0's ArUco boxes")
    return coordinates


def reference_points_from_dirs(prep_dir, predictions_path, verbose=True):
    """`reference_points_from_arrays`, reading the manifest and pointmap off disk."""
    manifest_path = os.path.join(prep_dir, "manifest.json")
    if not (os.path.exists(manifest_path) and os.path.exists(predictions_path)):
        return np.zeros((0, 3), dtype=np.float64)
    try:
        with open(manifest_path) as handle:
            manifest = json.load(handle)
        with np.load(predictions_path) as predictions:
            if "world_points" not in predictions:
                return np.zeros((0, 3), dtype=np.float64)
            return reference_points_from_arrays(
                manifest, predictions["world_points"],
                predictions["world_points_conf"], verbose)
    except (OSError, ValueError, KeyError) as exc:
        if verbose:
            print(f"  cube projection skipped: {type(exc).__name__}: {exc}")
        return np.zeros((0, 3), dtype=np.float64)
