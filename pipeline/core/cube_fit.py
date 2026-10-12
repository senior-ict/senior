"""Fit an ideal cube to the reference cube's points, and say how well it fits.

Stage 6's older check asked how much of its own oriented box the reference
cube's MESH fills. That number turned out to describe the mesh, not the
capture: on 21-24 September 2026 it warned on four of seven captures, and on
all seven an ideal cube fitted the POINTS to within 0.7-1.5 mm, at or below
the pipeline's own surface-noise floor. The loose alpha wrap that Stage 4
falls back to was what filled the box badly.

So this fits the shape we know. After levelling, the cube stands with its
faces upright, which leaves four unknowns: its side, its yaw about the
vertical, and where its centre sits. The fit minimises each point's distance
to that cube's surface. Two numbers come out of it:

  residual   how far EVERY point sits from a true cube, in millimetres. This is
             the capture check: a cube that did not reconstruct as a cube
             cannot have a small residual, however the mesher wrapped it.
  side       the cube's side in scene units, which is a second reading of the
             scale. Measured against the mesh-volume scale the pipeline uses,
             the two agree to about 1% (fitted sides 9.85-10.05 cm where the
             mesh-volume scale reads 10.00 by construction), so the fit is
             reported as a cross-check and does not set the scale.

A yaw sweep runs before any local fitting, because a cube fitted 45 degrees
out would wrap its own diagonal and read about 40% large; a local optimiser
started from the wrong angle would happily sit there.
"""
import numpy as np
from scipy.optimize import minimize

YAW_STEP_DEGREES = 2.0            # a cube repeats every quarter turn
POLISH_COUNT = 3                  # how many of the best sweep angles to refine
OUTLIER_ROUNDS = 2
OUTLIER_SPREAD_MULTIPLE = 3.0
EXTENT_PERCENTILE = 1.0           # robust stand-in for the min and max
MINIMUM_POINTS = 200


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


def guess_cube_at_yaw(points, yaw):
    """A quick cube for this yaw, from the points' robust extents; returns (centre_x, centre_y, bottom, side)."""
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    rotated_x = points[:, 0] * cosine - points[:, 1] * sine
    rotated_y = points[:, 0] * sine + points[:, 1] * cosine
    low_x, high_x = np.percentile(rotated_x, [EXTENT_PERCENTILE, 100 - EXTENT_PERCENTILE])
    low_y, high_y = np.percentile(rotated_y, [EXTENT_PERCENTILE, 100 - EXTENT_PERCENTILE])
    low_z, high_z = np.percentile(points[:, 2], [EXTENT_PERCENTILE, 100 - EXTENT_PERCENTILE])
    side = float(np.mean([high_x - low_x, high_y - low_y, high_z - low_z]))
    middle_x, middle_y = (low_x + high_x) / 2.0, (low_y + high_y) / 2.0
    # Back out of the rotated frame to get the centre in scene coordinates.
    centre_x = middle_x * cosine + middle_y * sine
    centre_y = -middle_x * sine + middle_y * cosine
    bottom = float((low_z + high_z) / 2.0 - side / 2.0)
    return float(centre_x), float(centre_y), bottom, side


def mean_squared_distance(points, yaw, centre_x, centre_y, bottom, side):
    """How badly this cube describes the points."""
    if side <= 0:
        return 1e6
    return float(np.mean(distance_to_cube_surface(points, yaw, centre_x, centre_y, bottom, side) ** 2))


def fit_cube(points):
    """Fit an ideal upright cube to levelled points.

    Returns {side, yaw_degrees, centre, bottom, residual, inlier_fraction} in
    the points' own units, or None when there are too few points.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < MINIMUM_POINTS:
        return None

    working = points
    best_parameters = None
    for _ in range(OUTLIER_ROUNDS):
        sweep = []
        for yaw_degrees in np.arange(0.0, 90.0, YAW_STEP_DEGREES):
            yaw = np.radians(yaw_degrees)
            centre_x, centre_y, bottom, side = guess_cube_at_yaw(working, yaw)
            cost = mean_squared_distance(working, yaw, centre_x, centre_y, bottom, side)
            sweep.append((cost, [yaw, centre_x, centre_y, bottom, side]))
        sweep.sort(key=lambda entry: entry[0])

        best_cost = None
        for _, start in sweep[:POLISH_COUNT]:
            def cost_of(values):
                """Mean squared distance for a cube described by yaw, centre, base and side."""
                return mean_squared_distance(working, values[0], values[1], values[2], values[3], values[4])

            polished = minimize(cost_of, start, method="Nelder-Mead",
                                options={"xatol": 1e-6, "fatol": 1e-12, "maxiter": 4000})
            if best_cost is None or polished.fun < best_cost:
                best_cost, best_parameters = float(polished.fun), polished.x

        distances = distance_to_cube_surface(points, *best_parameters[:4], best_parameters[4])
        spread = 1.4826 * np.median(np.abs(distances - np.median(distances)))
        working = points[distances <= np.median(distances) + OUTLIER_SPREAD_MULTIPLE * max(spread, 1e-9)]

    yaw, centre_x, centre_y, bottom, side = best_parameters
    distances = distance_to_cube_surface(points, yaw, centre_x, centre_y, bottom, side)
    spread = 1.4826 * np.median(np.abs(distances - np.median(distances)))
    inliers = distances <= np.median(distances) + OUTLIER_SPREAD_MULTIPLE * max(spread, 1e-9)
    # The residual is measured over EVERY point, not just the ones the fit
    # kept. Measured over the inliers alone it reported 1.88 mm for a cube
    # sheared 35% out of true (2026-09-24), because the rejection step had
    # already thrown the distorted points away -- the very thing the check
    # exists to notice.
    return {"side": float(side),
            "yaw_degrees": float(np.degrees(yaw) % 90.0),
            "centre": (float(centre_x), float(centre_y)),
            "bottom": float(bottom),
            "residual": float(np.sqrt(np.mean(distances ** 2))),
            "residual_inliers": float(np.sqrt(np.mean(distances[inliers] ** 2))),
            "inlier_fraction": float(inliers.mean())}


def fit_cube_from_ply(path):
    """Fit the cube in a levelled PLY of reference points, or None if it cannot be read."""
    try:
        import open3d as o3d

        points = np.asarray(o3d.io.read_point_cloud(str(path)).points)
    except Exception:
        return None
    return fit_cube(points)
