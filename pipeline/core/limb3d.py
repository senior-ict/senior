"""Points known to sit on the limb, from the mask Stage 0 already made.

Stage 3 has to say which reconstructed cluster is the limb and which is the
room. With a reference cube in the scene that question was answered by
projecting the cube's printed markers and taking the cluster that held them.
Without a cube there is nothing printed to project, and the decision falls
back to shape, which the report lists as a defect: a limb can win a shape
contest against a cube and nothing notices.

Stage 0 already segments the limb by name, through GroundingDINO and SAM, and
then throws the mask away after framing. Saving the eroded core of that mask
and projecting it here answers the same question from evidence instead. The
mask does not have to be accurate at the limb's edge. It has to be right in
the middle, which is the part a segmenter is most confident about.
"""

import os

import cv2
import numpy as np

from pipeline.core.bands3d import _frame_to_input_box

# Pixels below this confidence percentile within their own frame are not
# trusted to say where anything is. Matches the cube projection's threshold.
CONFIDENCE_PERCENTILE = 30.0

# Fewer trusted points than this under one frame's mask means the frame saw
# too little of the limb to be worth a vote.
FEWEST_POINTS_PER_FRAME = 32


def _mask_on_input_grid(mask, record, input_size, preprocess):
    """The limb mask resampled onto the grid the model actually consumed.

    The mask is drawn on the original frame, so each pixel of the model's
    input is mapped back to where it came from and the mask read there. That
    reuses the mapping the cube projection uses rather than inventing a
    second one that could disagree with it.
    """
    mapped = _frame_to_input_box(record, input_size, preprocess=preprocess)
    if mapped is None:
        return None
    origin, scale_x, scale_y, offset_y = mapped

    columns = np.arange(input_size, dtype=np.float64)
    rows = np.arange(input_size, dtype=np.float64)
    source_x = np.round(columns / scale_x + origin[0]).astype(int)
    source_y = np.round((rows + offset_y) / scale_y + origin[1]).astype(int)

    height, width = mask.shape[:2]
    inside_x = (source_x >= 0) & (source_x < width)
    inside_y = (source_y >= 0) & (source_y < height)
    source_x = np.clip(source_x, 0, width - 1)
    source_y = np.clip(source_y, 0, height - 1)

    sampled = mask[np.ix_(source_y, source_x)]
    sampled &= inside_y[:, None]
    sampled &= inside_x[None, :]
    return sampled


def limb_points_from_arrays(manifest, prep_dir, world_points, world_points_conf,
                            verbose=True):
    """Points that lie on the limb, in the model's own coordinates.

    Returns an empty array when Stage 0 left no masks behind, which is the
    normal state for a capture framed before this existed.
    """
    empty = np.empty((0, 3), dtype=np.float64)
    # Stage 0 writes the masks next to the frames it wrote, which is a folder
    # below the stage directory, so both places are checked.
    mask_dir = None
    for candidate in (os.path.join(prep_dir, "limb_mask"),
                      os.path.join(prep_dir, "images", "limb_mask")):
        if os.path.isdir(candidate):
            mask_dir = candidate
            break
    if mask_dir is None:
        return empty

    records = manifest.get("frames") or []
    input_size = int(world_points.shape[1])
    preprocess = manifest.get("vggt_preprocess") or "crop"

    collected = []
    frames_used = 0
    for frame_index, record in enumerate(records):
        if frame_index >= world_points.shape[0]:
            break
        mask_path = os.path.join(mask_dir, f"frame_{frame_index:02d}.png")
        if not os.path.exists(mask_path):
            continue
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue

        on_grid = _mask_on_input_grid(mask > 127, record, input_size, preprocess)
        if on_grid is None or not on_grid.any():
            continue

        frame_confidence = world_points_conf[frame_index]
        floor = float(np.percentile(frame_confidence, CONFIDENCE_PERCENTILE))
        keep = on_grid & (frame_confidence >= floor)
        if keep.sum() < FEWEST_POINTS_PER_FRAME:
            continue

        collected.append(world_points[frame_index][keep])
        frames_used += 1

    if not collected:
        if verbose:
            print("  limb projection: no confident 3D points under any limb mask")
        return empty

    coordinates = np.concatenate(collected).astype(np.float64)
    coordinates = coordinates[np.isfinite(coordinates).all(axis=1)]
    if verbose:
        print(f"  Limb projection: {len(coordinates):,} points on the limb "
              f"from {frames_used} frame(s) of Stage 0's mask")
    return coordinates
