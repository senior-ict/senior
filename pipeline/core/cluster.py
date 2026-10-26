"""DBSCAN clustering, then deciding which cluster is the reference cube.

The decision matters more than its size suggests: every centimetre the pipeline
reports is scaled from the reference cube's known 10 cm side, so labelling the
wrong cluster as the reference scales the whole measurement off the subject.

There are two ways of deciding here, and they are not equivalent.

**Evidence.** Stage 0 detected ArUco markers in the photographs and recorded
where they were; `core/cube3d.py` maps those boxes through Stage 1's pointmap
into the same space these clusters live in. A cluster that contains those points
*is* the cube, because a camera saw a marker there. Measured on five captures,
the cube's cluster holds 100% of its points within 1.5 cm of a projected marker
pixel and the limb's holds 0.0% -- the two are not close.

**Resemblance.** With no projection available, all that is left is how cube-like
a cluster looks: the ratio of its smallest bounding-box extent to its largest.
That is a property a thigh can have, so this path says out loud that it is
guessing.
"""
import numpy as np
from scipy.spatial import cKDTree

# How near a cluster point has to be to a projected marker pixel to count as
# the same surface, in VGGT world units. A 10 cm cube spans about 0.13 units, so
# 0.02 is roughly 1.5 cm -- wider than the reconstruction's own scatter on one
# face, far narrower than the gap between the cube and the limb.
REFERENCE_MATCH_TOLERANCE = 0.02

# The share of a cluster's own points that must sit on a projected marker pixel
# before the vote is believed, and how far ahead of the other cluster it has to
# be. Measured separation is 100% against 0.0%, so these are floors well below
# anything observed rather than a tuned boundary.
REFERENCE_MATCH_MIN_SHARE = 0.25
REFERENCE_MATCH_MARGIN = 4.0


def compute_eps(pcd, factor=4.0):
    """Estimate DBSCAN epsilon from average nearest-neighbor distance."""
    distances = pcd.compute_nearest_neighbor_distance()
    avg_dist = np.mean(distances)
    print(f"Avg NN distance: {avg_dist:.6f}")
    return avg_dist * factor


def get_cluster_info(cluster):
    """Return extent, density, and maximum dimension of one cluster."""
    bbox = cluster.get_axis_aligned_bounding_box()
    extent = bbox.get_extent()
    volume = np.prod(extent) if np.all(extent > 0) else 1e-6
    density = len(cluster.points) / volume
    max_dim = max(extent)
    return extent, density, max_dim


def aruco_cubeness(cluster):
    """Score 0..1: how cube-like the cluster bbox is (ArUco = 14cm cube → ~1.0)."""
    extent = cluster.get_axis_aligned_bounding_box().get_extent()
    mx = float(np.max(extent))
    if mx <= 1e-9:
        return 0.0
    return float(np.min(extent) / mx)


def aruco_bw_ratio(cluster):
    """Score 0..1: fraction of points near-black or near-white (ArUco signature)."""
    if not cluster.has_colors():
        return 0.0
    colors = np.asarray(cluster.colors)
    if len(colors) == 0:
        return 0.0
    brightness = colors.mean(axis=1)
    frac_black = float((brightness < 0.20).mean())
    frac_white = float((brightness > 0.80).mean())
    return frac_black + frac_white


def reference_match_share(cluster, reference_points):
    """Share of this cluster's points that sit on a projected marker pixel.

    `reference_points` is an (N, 3) array from `core/cube3d.py`: positions that
    a camera saw an ArUco marker at, in this same unlevelled VGGT space.
    Returns 0.0 when there is nothing to compare against.
    """
    points = np.asarray(cluster.points)
    if len(points) == 0 or reference_points is None or len(reference_points) == 0:
        return 0.0
    tree = cKDTree(np.asarray(reference_points))
    distances, _ = tree.query(points)
    return float((distances < REFERENCE_MATCH_TOLERANCE).mean())


def identify_reference_cluster(clusters, reference_points):
    """Which of these clusters is the reference cube, and on what grounds.

    Returns (index, grounds) where grounds is "projected ArUco markers" when
    the decision rests on evidence and "cubeness only (a guess)" when it rests
    on shape alone.
    """
    shares = []
    for cluster in clusters:
        shares.append(reference_match_share(cluster, reference_points))

    best_index = int(np.argmax(shares))
    best_share = shares[best_index]
    runner_up_share = 0.0
    for index, share in enumerate(shares):
        if index != best_index and share > runner_up_share:
            runner_up_share = share

    clears_floor = best_share >= REFERENCE_MATCH_MIN_SHARE
    clears_margin = best_share >= REFERENCE_MATCH_MARGIN * runner_up_share
    if clears_floor and clears_margin:
        detail = ", ".join(f"#{index + 1}={share:.1%}"
                           for index, share in enumerate(shares))
        print(f"    ArUco projection: {detail} of each cluster's points sit on "
              f"a marker pixel")
        return best_index, "projected ArUco markers"

    if any(share > 0.0 for share in shares):
        print(f"    ArUco projection inconclusive: best {best_share:.1%} vs "
              f"{runner_up_share:.1%} — needs {REFERENCE_MATCH_MIN_SHARE:.0%} "
              f"and a {REFERENCE_MATCH_MARGIN:g}x lead")

    cubeness_scores = [aruco_cubeness(cluster) for cluster in clusters]
    fallback_index = int(np.argmax(cubeness_scores))
    print("    WARNING: no marker evidence — the reference is being chosen by "
          "cubeness alone, which a limb can win. Every measurement from this "
          "run is scaled off that choice.")
    return fallback_index, "cubeness only (a guess)"


def detect_top_k_objects(pcd, k=2, visualize=False, reference_points=None):
    """Detect top-k clusters, then identify which one is the reference cube.

    Returns: (box_cluster, obj_cluster)
        box_cluster  — the reference cube, whose known side sets the scale
        obj_cluster  — the subject being measured
        Returns (pcd, None) if only 1 cluster found.

    `reference_points` is the ArUco projection from `core/cube3d.py`. Given it,
    the identification is decided by which cluster holds those points. Without
    it the shape heuristic decides and says that it guessed.
    """
    del visualize  # currently unused; reserved for future debug viewer
    print("Running DBSCAN...")
    eps = compute_eps(pcd)
    print(f"Adaptive eps: {eps:.5f}")

    labels = np.array(pcd.cluster_dbscan(eps=eps, min_points=10))
    valid = labels >= 0

    if not np.any(valid):
        print("No clusters found → using whole cloud as single object")
        return (pcd, None)

    unique_ids = np.unique(labels[valid])
    print(f"Total clusters found: {len(unique_ids)}")

    min_points = 0.01 * len(pcd.points)

    clusters = []
    for cid in unique_ids:
        idx = np.where(labels == cid)[0]
        cluster = pcd.select_by_index(idx)
        extent, density, max_dim = get_cluster_info(cluster)
        npts = len(cluster.points)

        if npts < min_points:
            continue

        clusters.append((cluster, npts, extent, density, max_dim))

    if len(clusters) == 0:
        print("No valid clusters → using whole cloud")
        return (pcd, None)

    # Adaptive scoring: normalize by data median instead of magic constants
    npts_arr = np.array([c[1] for c in clusters])
    dens_arr = np.array([c[3] for c in clusters])
    dims_arr = np.array([c[4] for c in clusters])

    med_pts = max(float(np.median(npts_arr)), 1.0)
    med_dens = max(float(np.median(dens_arr)), 1.0)
    max_dim_val = max(float(np.max(dims_arr)), 1e-6)

    scored = []
    for i, (cluster, npts, extent, density, max_dim) in enumerate(clusters):
        norm_pts = npts / med_pts
        norm_dens = density / med_dens
        norm_compact = 1.0 - (max_dim / max_dim_val)
        score = norm_pts * 0.4 + norm_dens * 0.3 + norm_compact * 0.3
        scored.append((cluster, score, npts, extent, density, max_dim))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:min(k, len(scored))]

    if len(top) < 2:
        print("Only 1 cluster → returning as box, no obj")
        return (top[0][0], None)

    # Reference identification. The printed cubeness and black-white scores are
    # kept because they are what a reviewer compares against when the vote and
    # the shape heuristic disagree, but they no longer decide anything on their
    # own once the projection is available.
    #
    # The score that used to decide here was `cubeness * 0.3 + black_white * 0.7`
    # with a branch reading: if any cluster scores above 0.7, label THAT one the
    # marker and the other one the reference. That branch was inverted against
    # this function's present meaning -- a cube reconstructed well enough to look
    # black-and-white would have been discarded and the limb scaled from instead.
    # It never fired (observed scores 0.09-0.53), which is the only reason it
    # never did harm.
    print("\n  Reference identification:")
    candidates = []
    for index, (cluster, score, npts, extent, density, max_dim) in enumerate(top):
        cubeness = aruco_cubeness(cluster)
        black_white = aruco_bw_ratio(cluster)
        extent_text = f"({extent[0]:.4f},{extent[1]:.4f},{extent[2]:.4f})"
        print(f"    cluster #{index+1}: {npts:,} pts, cubeness={cubeness:.4f}, "
              f"black/white={black_white:.3f} {extent_text}")
        candidates.append(cluster)

    box_idx, grounds = identify_reference_cluster(candidates, reference_points)
    obj_idx = 1 - box_idx

    print(f"    → cluster #{box_idx+1}: {len(top[box_idx][0].points):,} pts — "
          f"REFERENCE (box.ply), by {grounds}")
    print(f"    → cluster #{obj_idx+1}: {len(top[obj_idx][0].points):,} pts — "
          f"SUBJECT (obj.ply)")

    return (top[box_idx][0], top[obj_idx][0])
