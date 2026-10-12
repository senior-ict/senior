"""MLS with an ellipsoidal neighbourhood instead of a sphere.

The pipeline's `mls_project` (pipeline/ghost.py) gathers every neighbour inside
a sphere, fits a degree-2 height field over the local tangent plane, and moves
the point onto it. This variant keeps that fit exactly and changes only which
neighbours take part: an ellipsoid with one radius along the local normal and
another in the tangent plane.

Why that matters here: the ghost double sheet is two copies of the surface
about a centimetre apart ALONG THE NORMAL, while everything worth preserving --
the tibial ridge, the calf bulge, the ankle narrowing -- is structure ALONG THE
TANGENT. A sphere wide enough to bridge the sheets is also wide enough to
flatten the anatomy; an ellipsoid can reach one without the other.

The normal each ellipsoid is oriented by is estimated first from a small
sphere, because the wide neighbourhood is exactly where a normal is unreliable.
Only its axis is used, so its sign does not matter.
"""
import numpy as np


def mls_project_ellipsoid(points, normal_mult, tangent_mult, normal_estimate_mult=6.0,
                          min_neighbors=8):
    """Project every point onto a degree-2 surface fitted to an ellipsoidal patch.

    Args:
        points: (N, 3) float.
        normal_mult: ellipsoid semi-axis along the local normal, in multiples
            of mean nearest-neighbour spacing.
        tangent_mult: ellipsoid semi-axis in the tangent plane, same units.
        normal_estimate_mult: radius of the small sphere used to estimate each
            point's normal before the ellipsoid is oriented.
        min_neighbors: below this a point is left where it is.

    Returns:
        (points_projected, stats dict)
    """
    from scipy.spatial import cKDTree

    points = np.asarray(points, dtype=np.float64)
    point_count = len(points)
    if point_count < min_neighbors:
        return points, {"skipped": point_count}

    tree = cKDTree(points)
    sample = np.random.default_rng(0).choice(point_count, min(5000, point_count), replace=False)
    nearest, _ = tree.query(points[sample], k=2, workers=-1)
    spacing = float(nearest[:, 1].mean())

    normal_radius = spacing * normal_mult
    tangent_radius = spacing * tangent_mult
    outer_radius = max(normal_radius, tangent_radius)

    # Normals from a small sphere, so two sheets do not confuse the estimate.
    small_neighbourhoods = tree.query_ball_point(points, r=spacing * normal_estimate_mult,
                                                workers=-1)
    normals = np.zeros_like(points)
    for index, neighbour_indices in enumerate(small_neighbourhoods):
        if len(neighbour_indices) < 3:
            normals[index] = (0.0, 0.0, 1.0)
            continue
        local = points[neighbour_indices] - points[neighbour_indices].mean(axis=0)
        _, _, axes = np.linalg.svd(local, full_matrices=False)
        normals[index] = axes[2]

    # Candidates from the enclosing sphere, then trimmed to the ellipsoid.
    outer_neighbourhoods = tree.query_ball_point(points, r=outer_radius, workers=-1)

    projected = points.copy()
    moved = np.zeros(point_count)
    skipped = 0
    for index, candidate_indices in enumerate(outer_neighbourhoods):
        candidates = points[candidate_indices]
        offsets = candidates - points[index]
        along_normal = offsets @ normals[index]
        tangential = offsets - np.outer(along_normal, normals[index])
        inside = ((along_normal / normal_radius) ** 2
                  + (np.linalg.norm(tangential, axis=1) / tangent_radius) ** 2) <= 1.0
        neighbours = candidates[inside]
        if len(neighbours) < min_neighbors:
            skipped += 1
            continue

        # From here on this is the pipeline's own fit, unchanged.
        centre = neighbours.mean(axis=0)
        centred = neighbours - centre
        _, _, axes = np.linalg.svd(centred, full_matrices=False)
        normal, tangent_u, tangent_v = axes[2], axes[0], axes[1]
        offset_u, offset_v, height = centred @ tangent_u, centred @ tangent_v, centred @ normal

        if len(neighbours) >= 6:
            design = np.column_stack([np.ones_like(offset_u), offset_u, offset_v,
                                      offset_u * offset_u, offset_u * offset_v,
                                      offset_v * offset_v])
        else:
            design = np.column_stack([np.ones_like(offset_u), offset_u, offset_v])
        try:
            coefficients, *_ = np.linalg.lstsq(design, height, rcond=None)
        except np.linalg.LinAlgError:
            skipped += 1
            continue
        if len(coefficients) == 3:
            coefficients = np.concatenate([coefficients, np.zeros(3)])

        this_u = float((points[index] - centre) @ tangent_u)
        this_v = float((points[index] - centre) @ tangent_v)
        fitted_height = (coefficients[0] + coefficients[1] * this_u + coefficients[2] * this_v
                         + coefficients[3] * this_u * this_u
                         + coefficients[4] * this_u * this_v
                         + coefficients[5] * this_v * this_v)
        target = centre + this_u * tangent_u + this_v * tangent_v + fitted_height * normal
        moved[index] = np.linalg.norm(target - points[index])
        projected[index] = target

    stats = {"spacing": spacing, "normal_radius": normal_radius,
             "tangent_radius": tangent_radius,
             "median_move": float(np.median(moved)),
             "p95_move": float(np.percentile(moved, 95)), "skipped": skipped}
    return projected.astype(np.float32), stats
