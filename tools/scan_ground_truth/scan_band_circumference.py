"""Measure limb circumference at the marker bands, from a 3D scan.

Two things have to be right for this to mean what the tape means.

Where. The tape is laid on the leg immediately inside a band, not over it, so
what it reads is the leg alone and not the leg plus the cord. "Inside" means
the side facing the other band, and the two bands therefore have their inner
edges facing each other. Measuring over the band adds the cord's thickness,
and averaging a slab on both sides of a band mixes a plane inside the pair
with one outside it, which on a tapering calf are different circumferences.

What. A tape pulled round a limb cannot dip into a hollow, so it reads the
perimeter of the convex hull of the cross-section rather than its true
outline. That is what is computed here, in the plane of the band.
"""

import argparse
import gc
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull

LEAST_GREENNESS = 0.12
SMALLEST_BAND = 400

# An arc smaller than this is a speck of something green, not part of a
# band. A reconstruction builds each band as a few broken arcs, so this
# has to be well below a whole ring.
SMALLEST_ARC = 60
CLUSTER_REACH_MM = 6.0


def excess_green(colours):
    """How much greener than grey each colour is."""
    return 2.0 * colours[:, 1] - colours[:, 0] - colours[:, 2]


def plane_of(points):
    """Centroid and unit normal of the best-fitting plane through points."""
    centre = points.mean(axis=0)
    _, _, directions = np.linalg.svd(points - centre, full_matrices=False)
    return centre, directions[2]


def hull_perimeter(points, centre, normal):
    """Perimeter of the convex hull of points projected onto a plane, in mm."""
    first = np.cross(normal, [1.0, 0.0, 0.0])
    if np.linalg.norm(first) < 1e-6:
        first = np.cross(normal, [0.0, 1.0, 0.0])
    first = first / np.linalg.norm(first)
    second = np.cross(normal, first)

    offsets = points - centre
    flat = np.stack([offsets @ first, offsets @ second], axis=1)
    hull = ConvexHull(flat)
    loop = flat[hull.vertices]
    closed = np.vstack([loop, loop[:1]])
    return float(np.sum(np.linalg.norm(np.diff(closed, axis=0), axis=1)))


def limb_at_inner_edge(all_points, green, centre, normal, inner_sign,
                       inner_edge_mm, reach_mm, thickness_mm=3.0):
    """The leg's circumference just inside a band, where the tape was laid.

    The slab starts at the band's inner edge and reaches a few millimetres
    further in. Green points are left out so a stray bit of cord cannot pad
    the hull, and the slab is cut down to what lies near the limb's own axis
    so the other leg and the floor cannot join it.
    """
    along = (all_points - centre) @ normal
    sideways = np.linalg.norm(
        (all_points - centre) - np.outer(along, normal), axis=1)

    inward = along * inner_sign
    starts_at = inner_edge_mm * inner_sign
    wanted = ((inward >= starts_at) & (inward <= starts_at + thickness_mm)
              & (sideways <= reach_mm) & ~green)
    if wanted.sum() < 200:
        return float("nan"), int(wanted.sum())

    middle = centre + normal * (starts_at + thickness_mm / 2.0) * inner_sign
    return hull_perimeter(all_points[wanted], middle, normal), int(wanted.sum())


def band_edges(ring, centre, normal):
    """Where a band starts and ends along the limb, in mm from its centre."""
    along = (ring - centre) @ normal
    low, high = np.quantile(along, [0.02, 0.98])
    return float(low), float(high)


def main():
    """Report both band circumferences for one scan."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--mm-per-unit", type=float, default=1.0,
                        help="multiply coordinates by this to reach "
                             "millimetres. A scan is already in millimetres; "
                             "a reconstruction is in its own units and needs "
                             "the scale stage 6 derived.")
    arguments = parser.parse_args()

    mesh = o3d.io.read_triangle_mesh(arguments.scan)
    points = np.asarray(mesh.vertices)
    colours = np.asarray(mesh.vertex_colors)
    if len(points) == 0:
        cloud = o3d.io.read_point_cloud(arguments.scan)
        points = np.asarray(cloud.points)
        colours = np.asarray(cloud.colors)
        del cloud
    points = points * arguments.mm_per_unit
    del mesh
    gc.collect()

    green = excess_green(colours)
    on_band = green >= LEAST_GREENNESS
    if on_band.sum() < SMALLEST_BAND:
        print(f"{arguments.label}: only {on_band.sum()} green points, giving up")
        return

    band_points = points[on_band]

    # Two steps, because neither alone works on both kinds of input.
    # First drop stray green specks, which on a scan can sit anywhere in the
    # room and would otherwise decide the direction everything is measured
    # along. Then split what survives into two bands by where it sits along
    # the line joining them: the bands are about 27 cm apart and only about
    # 9 cm across, so that separates cleanly. Grouping in three dimensions
    # instead fails on a reconstruction, where only one side of the limb is
    # built and each band arrives as two or three broken arcs.
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(band_points))
    labels = np.array(cloud.cluster_dbscan(eps=CLUSTER_REACH_MM, min_points=10))
    solid = np.zeros(len(band_points), dtype=bool)
    for label in range(labels.max() + 1):
        chosen = labels == label
        if chosen.sum() >= SMALLEST_ARC:
            solid |= chosen
    if solid.sum() < SMALLEST_BAND:
        print(f"{arguments.label}: only {solid.sum()} band points survive, giving up")
        return
    band_points = band_points[solid]

    centred = band_points - band_points.mean(axis=0)
    _, _, directions = np.linalg.svd(centred, full_matrices=False)
    along = centred @ directions[0]

    split = 0.5 * (np.quantile(along, 0.02) + np.quantile(along, 0.98))
    rings = [band_points[along < split], band_points[along >= split]]
    rings = [ring for ring in rings if len(ring) >= SMALLEST_BAND]

    if len(rings) < 2:
        print(f"{arguments.label}: found {len(rings)} band(s), expected 2")
        return

    # Name them by position along the limb, which runs between the two bands.
    centres = [ring.mean(axis=0) for ring in rings]
    axis = centres[1] - centres[0]
    axis = axis / np.linalg.norm(axis)
    gap_mm = float(np.linalg.norm(centres[1] - centres[0]))

    measured = []
    for ring in rings:
        centre, normal = plane_of(ring)
        # Point the normal along the limb, from this band toward the other.
        other = [entry for entry in rings if entry is not ring][0]
        toward_other = other.mean(axis=0) - centre
        if normal @ toward_other < 0:
            normal = -normal

        low_edge, high_edge = band_edges(ring, centre, normal)
        # With the normal pointing inward, the inner edge is the far one.
        inner_edge = high_edge
        band = hull_perimeter(ring, centre, normal)
        reach = 0.9 * band / np.pi

        leg, used = limb_at_inner_edge(points, on_band, centre, normal, 1.0,
                                       inner_edge, reach)
        measured.append({"centre": centre, "band": band, "leg": leg,
                         "width": high_edge - low_edge, "count": len(ring),
                         "slab_points": used, "inner_edge": inner_edge})

    inner_gap = gap_mm - sum(entry["inner_edge"] for entry in measured)

    order = np.argsort([entry["band"] for entry in measured])
    print(f"\n{arguments.label}")
    print(f"   bands {gap_mm / 10.0:.2f} cm apart centre to centre, "
          f"{inner_gap / 10.0:.2f} cm inner edge to inner edge")
    print("              width   over the band   leg at inner edge   slab pts")
    for name, index in zip(("lower", "upper"), order):
        entry = measured[index]
        print(f"   {name:6}   {entry['width']:5.1f} mm   {entry['band'] / 10.0:8.2f} cm"
              f"   {entry['leg'] / 10.0:12.2f} cm   {entry['slab_points']:7d}")


if __name__ == "__main__":
    main()
