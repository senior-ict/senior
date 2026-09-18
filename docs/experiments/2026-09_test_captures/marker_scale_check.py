"""Check the cube-volume scale against the 5 cm ArUco markers VGGT saw.

Stage 6 scales the scene from the reconstructed cube's mesh volume:
cm-per-unit = (10^3 / volume) ** (1/3). This script measures the same scale a
second way that needs no mesh. On every frame VGGT was given, it detects the
markers, reads the predicted 3D point under each marker corner, and measures
the marker's edges in scene units. The printed marker is 5.0 cm, so the ratio
5.0 / edge is a cm-per-unit that depends only on the point map. If the cube's
mesh volume is inflating or deflating the scale, the two disagree.

It also reports the marker edges split by their direction in the photograph,
which shows whether VGGT stretches one axis more than the other, the green
band separation on the cleaned cloud, and the cube mesh's extents by axis.

    python docs/experiments/2026-09_test_captures/marker_scale_check.py output_test6_mls16 output_test5
"""
import pathlib
import sys

import cv2
import numpy as np
import open3d as o3d
import trimesh

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]

MARKER_CM = 5.0
CUBE_CM = 10.0
DICTIONARY_NAME = "DICT_5X5_250"
DETECT_UPSCALE = 3      # the 518 px frames are small; detect on an enlarged copy
CORNER_WINDOW = 1       # 3x3 window of point-map pixels around each corner
POINT_SOURCES = {"pointmap": ("world_points", "world_points_conf"),
                 "depth": ("world_points_from_depth", "depth_conf")}


def detect_markers(image_rgb_float):
    """Marker ids and corner pixels on one 518 px frame, detected on an enlarged copy."""
    image_uint8 = (np.clip(image_rgb_float, 0, 1) * 255).astype(np.uint8)
    gray = cv2.cvtColor(image_uint8, cv2.COLOR_RGB2GRAY)
    enlarged = cv2.resize(gray, None, fx=DETECT_UPSCALE, fy=DETECT_UPSCALE,
                          interpolation=cv2.INTER_CUBIC)
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY_NAME))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corner_sets, marker_ids, _ = detector.detectMarkers(enlarged)
    if marker_ids is None:
        return []
    detections = []
    for marker_id, corners in zip(marker_ids.ravel(), corner_sets):
        detections.append((int(marker_id), corners.reshape(4, 2) / DETECT_UPSCALE))
    return detections


def point_under_corner(world_points, confidence, corner_pixel):
    """Median 3D point in a small window around a corner pixel.

    A marker corner sits on a black/white edge where the point map is noisy,
    so the median of the better-confidence half of a 3x3 window is used rather
    than the single pixel.
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


def marker_edges(world_points, confidence, corners):
    """Each edge of one marker: its length in scene units and its direction in the image.

    The direction is 'vertical' or 'horizontal' when the edge runs mostly one
    way in the photograph, else 'oblique'. With the phone held roughly level
    that is also the edge's direction in the world.
    """
    corner_points = np.array([point_under_corner(world_points, confidence, corner)
                              for corner in corners])
    edges = []
    for index in range(4):
        next_index = (index + 1) % 4
        length = np.linalg.norm(corner_points[next_index] - corner_points[index])
        image_step = corners[next_index] - corners[index]
        if abs(image_step[1]) > 2.5 * abs(image_step[0]):
            direction = "vertical"
        elif abs(image_step[0]) > 2.5 * abs(image_step[1]):
            direction = "horizontal"
        else:
            direction = "oblique"
        edges.append((length, direction))
    return edges


def green_band_separation(cleaned_cloud_path):
    """Vertical distance between the two green bands on the cleaned cloud, in scene units.

    Green points are histogrammed by height; the two tallest well-separated
    bins are the bands, and each band's height is the median of the green
    points near its bin. Returns None when there are too few green points.
    """
    cloud = o3d.io.read_point_cloud(str(cleaned_cloud_path))
    points = np.asarray(cloud.points)
    colours = np.asarray(cloud.colors)
    if len(colours) == 0:
        return None
    red, green, blue = colours[:, 0], colours[:, 1], colours[:, 2]
    is_green = (green > red * 1.25) & (green > blue * 1.25) & (green > 0.25)
    if is_green.sum() < 50:
        return None
    heights = points[is_green, 2]
    counts, bin_edges = np.histogram(heights, bins=60)
    bins_by_count = np.argsort(counts)[::-1]
    first_bin = bins_by_count[0]
    second_bin = next(candidate for candidate in bins_by_count if abs(candidate - first_bin) > 6)
    lower_edge, upper_edge = sorted([bin_edges[first_bin], bin_edges[second_bin]])
    half_width = (bin_edges[1] - bin_edges[0]) * 3
    lower_height = np.median(heights[(heights > lower_edge - half_width) & (heights < lower_edge + half_width)])
    upper_height = np.median(heights[(heights > upper_edge - half_width) & (heights < upper_edge + half_width)])
    return upper_height - lower_height


def analyse_run(run_name):
    """Print the two scales, the edge directions, the band separation and the cube extents."""
    debug_root = PROJECT_ROOT / run_name / "for_debug"
    predictions = np.load(debug_root / "01_inference/predictions.npz")
    box_mesh = trimesh.load(str(debug_root / "05_watertight/mesh/box.ply"), process=False)
    cube_scale_cm = (CUBE_CM ** 3 / abs(box_mesh.volume)) ** (1.0 / 3.0)
    cube_extents_cm = (box_mesh.bounds[1] - box_mesh.bounds[0]) * cube_scale_cm

    print(f"\n=== {run_name}")
    print(f"cube-volume scale        {cube_scale_cm:.4f} cm/unit")
    print(f"cube mesh extents        x {cube_extents_cm[0]:.2f}  y {cube_extents_cm[1]:.2f}  "
          f"z(up) {cube_extents_cm[2]:.2f} cm at cube scale")

    separation_units = green_band_separation(debug_root / "03_clean/objects/leg.ply")
    if separation_units is not None:
        print(f"green band separation    {separation_units * cube_scale_cm:.2f} cm at cube scale")

    images = predictions["images"].transpose(0, 2, 3, 1)
    for source_name, (points_key, confidence_key) in POINT_SOURCES.items():
        lengths_by_direction = {"vertical": [], "horizontal": [], "oblique": []}
        frames_with_markers = 0
        for frame_index, image in enumerate(images):
            detections = detect_markers(image)
            if detections:
                frames_with_markers += 1
            for _, corners in detections:
                edges = marker_edges(predictions[points_key][frame_index],
                                     predictions[confidence_key][frame_index], corners)
                for length, direction in edges:
                    lengths_by_direction[direction].append(length)
        all_lengths = sum(lengths_by_direction.values(), [])
        if not all_lengths:
            print(f"[{source_name}] no markers detected")
            continue
        edge_units = np.median(all_lengths)
        marker_scale_cm = MARKER_CM / edge_units
        vertical_cm = np.median(lengths_by_direction["vertical"]) * cube_scale_cm
        horizontal_cm = np.median(lengths_by_direction["horizontal"]) * cube_scale_cm
        print(f"[{source_name}] {frames_with_markers}/{len(images)} frames, {len(all_lengths)} edges: "
              f"marker edge {edge_units * cube_scale_cm:.3f} cm at cube scale (true 5.00); "
              f"vertical {vertical_cm:.3f}, horizontal {horizontal_cm:.3f}")
        print(f"[{source_name}] marker scale {marker_scale_cm:.4f} cm/unit; "
              f"marker/cube = {marker_scale_cm / cube_scale_cm:.4f} linear, "
              f"{(marker_scale_cm / cube_scale_cm) ** 3:.4f} volume")
        if separation_units is not None:
            print(f"[{source_name}] band separation {separation_units * marker_scale_cm:.2f} cm at marker scale")


def main():
    """Analyse every run directory named on the command line."""
    for run_name in sys.argv[1:]:
        analyse_run(run_name)


if __name__ == "__main__":
    main()
