"""A second scale for the scene, from the ArUco markers instead of the cube's mesh.

Stage 6 scales everything from the reconstructed cube's mesh volume. That
mesh is the product of every cleaning and reconstruction step, so when one of
them goes wrong on the cube (a Poisson failure that falls back to an alpha
wrap, a ghost sheet that survives) the scale moves with it, silently, and
every volume in the run moves too.

The markers printed on the cube give an independent scale that needs no
mesh: on every frame the model saw, detect the markers, read the model's 3D
point under each corner, and measure the marker's edges in scene units. The
marker is REFERENCE_MARKER_CM on a side, so cm-per-unit is that over the
median edge. On sound captures the two scales agree within 2-3%; on the
2026-09-19 run of inputs/test6 from full-resolution originals, where the cube
fell to the alpha fallback, they disagreed by 6%.
"""
import cv2
import numpy as np

from pipeline.config import REFERENCE_MARKER_CM, REFERENCE_MARKER_DICT

# The frames the model saw are 518 px; the markers on them are small, so
# detection runs on an enlarged copy and the corners are scaled back.
DETECT_UPSCALE = 3
# Half-width, in pixels, of the window of point-map pixels around each corner.
CORNER_WINDOW = 1


def detect_marker_corners(image_rgb_float, dict_name=REFERENCE_MARKER_DICT):
    """Corner pixels of every marker on one frame, as (4, 2) arrays."""
    image_uint8 = (np.clip(image_rgb_float, 0.0, 1.0) * 255).astype(np.uint8)
    gray = cv2.cvtColor(image_uint8, cv2.COLOR_RGB2GRAY)
    enlarged = cv2.resize(gray, None, fx=DETECT_UPSCALE, fy=DETECT_UPSCALE,
                          interpolation=cv2.INTER_CUBIC)
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corner_sets, marker_ids, _ = detector.detectMarkers(enlarged)
    if marker_ids is None:
        return []
    corners_per_marker = []
    for corners in corner_sets:
        corners_per_marker.append(corners.reshape(4, 2) / DETECT_UPSCALE)
    return corners_per_marker


def point_under_corner(world_points, confidence, corner_pixel):
    """Median 3D point of the better-confidence half of a small window at a corner.

    A marker corner sits on a black/white edge where the point map is noisy,
    so one pixel is not trusted on its own.
    """
    column, row = corner_pixel
    row_index = int(round(row))
    column_index = int(round(column))
    rows = slice(max(row_index - CORNER_WINDOW, 0), row_index + CORNER_WINDOW + 1)
    columns = slice(max(column_index - CORNER_WINDOW, 0), column_index + CORNER_WINDOW + 1)
    patch = world_points[rows, columns].reshape(-1, 3)
    patch_confidence = confidence[rows, columns].reshape(-1)
    keep = patch_confidence >= np.percentile(patch_confidence, 50)
    return np.median(patch[keep], axis=0)


def marker_edge_lengths(world_points, confidence, corners):
    """The four edge lengths of one marker in scene units."""
    corner_points = []
    for corner in corners:
        corner_points.append(point_under_corner(world_points, confidence, corner))
    lengths = []
    for index in range(4):
        next_index = (index + 1) % 4
        lengths.append(float(np.linalg.norm(corner_points[next_index] - corner_points[index])))
    return lengths


def marker_scale_from_predictions(predictions_path, marker_cm=REFERENCE_MARKER_CM):
    """cm-per-unit from the markers in a Stage 1 prediction file, or None.

    Returns a dict with `cm_per_unit`, `edge_count` and `frames_with_markers`,
    or None when no marker was found on any frame.
    """
    predictions = np.load(predictions_path)
    images = predictions["images"].transpose(0, 2, 3, 1)
    world_points = predictions["world_points"]
    confidence = predictions["world_points_conf"]

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
    median_edge_units = float(np.median(all_lengths))
    return {"cm_per_unit": marker_cm / median_edge_units,
            "edge_count": len(all_lengths),
            "frames_with_markers": frames_with_markers}
