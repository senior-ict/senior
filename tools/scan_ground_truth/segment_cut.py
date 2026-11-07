"""Cut a mesh to the segment lying between two planes, and cap the two faces.

This mirrors what `pipeline/core/meshcut.py` does to a reconstruction, kept as
its own copy on purpose. The ground truth has to be measurable from any branch,
including the older pipelines that predate that module, and a reference that
only reproduces on one branch is not much of a reference.

The two implementations agree by construction: both take a capped plane slice
per marker, keep what lies between them, and then keep only the piece the bands
are tied round. Verified on 6_3d_scanner_2k, where both routes return 1566.8 cm3.

That last step is not decoration. Without it the scan of 6_3d_scanner_1k cut
into 14 pieces, the girth hull wrapped several at once, and the ankle band read
45.19 cm, wider than the knee. The scan was written off as unusable on the
strength of that number. It was this tool that was wrong.

One difference from the pipeline's copy: a reconstruction has been levelled, so
there "plan view" means x and y. A scan arrives in the scanner's own frame, so
here the view is taken along the band normal, which is the limb's own axis. The
two agree whenever the limb stands upright.
"""

import numpy as np

MIN_FACES_AFTER_CUT = 50

# Dropping a piece must never leave less than a cut would, on the same reasoning
# as MIN_FACES_AFTER_CUT: a selection that throws away the limb has failed.
MIN_FACES_AFTER_SELECTION = 50


def cut_between_planes(mesh, planes):
    """Keep only the part of a mesh lying between two planes, capping each cut.

    Each plane is a dict with a "centroid" and a "normal". The normals are
    expected to point at each other, so the wanted segment is on the positive
    side of both, and the cord each plane sits on falls outside it.

    Returns (cut_mesh, case_label). The mesh comes back uncut, with a label
    saying why, whenever the cut would leave almost nothing behind.
    """
    if len(planes) != 2:
        return mesh, "need_exactly_two_planes"

    cut = mesh
    for plane in planes:
        origin = np.asarray(plane["centroid"], dtype=np.float64)
        normal = np.asarray(plane["normal"], dtype=np.float64)
        normal = normal / (np.linalg.norm(normal) + 1e-8)
        cut = cut.slice_plane(plane_origin=origin, plane_normal=normal,
                              cap=True)
        if cut is None or len(cut.faces) == 0:
            return mesh, "cut_removed_everything"
        cut.merge_vertices()

    if len(cut.faces) < MIN_FACES_AFTER_CUT:
        return mesh, "too_few_after_cut"

    cut = _keep_the_piece_the_bands_encircle(cut, planes)
    return cut, "case_2_between"


def _viewing_axes(planes):
    """Returns two unit axes spanning the view taken along the limb's own axis.

    The band normals point along the limb, so looking down one of them gives the
    view in which a band is a ring and the limb is the thing inside it.
    """
    normal = np.asarray(planes[0]["normal"], dtype=np.float64)
    normal = normal / (np.linalg.norm(normal) + 1e-8)

    sideways = np.cross(normal, [0.0, 0.0, 1.0])
    if np.linalg.norm(sideways) < 1e-6:
        sideways = np.cross(normal, [0.0, 1.0, 0.0])
    sideways = sideways / np.linalg.norm(sideways)
    return sideways, np.cross(normal, sideways)


def _outsideness(points, band_centres, first_axis, second_axis):
    """How far outside a piece's outline the band centres fall, seen along the axis.

    Returns the largest signed distance over the band centres, negative when every
    centre lies inside the outline, or None when the piece has no usable outline.
    """
    try:
        from scipy.spatial import ConvexHull, QhullError
    except ImportError:
        return None

    flattened = np.column_stack([points @ first_axis, points @ second_axis])
    if len(flattened) < 3:
        return None
    try:
        outline = ConvexHull(flattened)
    except QhullError:
        return None

    worst = -np.inf
    for centre in band_centres:
        flat_centre = np.array([centre @ first_axis, centre @ second_axis])
        signed = outline.equations[:, :2] @ flat_centre + outline.equations[:, 2]
        worst = max(worst, float(signed.max()))
    return worst


def _keep_the_piece_the_bands_encircle(cut, planes):
    """Of the solids the cut left behind, keep the one the bands are tied round.

    A scan carries the floor, the other foot and any stray shell the scanner
    picked up, and the slab between two planes keeps every one of them that
    passes through it. Height cannot tell them apart, because they share the
    slab. The bands can, because they are tied round the limb and nothing else.
    """
    pieces = cut.split(only_watertight=False)
    if len(pieces) < 2:
        return cut

    first_axis, second_axis = _viewing_axes(planes)
    band_centres = [np.asarray(plane["centroid"], dtype=np.float64)
                    for plane in planes]

    best_piece = None
    best_outsideness = None
    for piece in pieces:
        points = np.asarray(piece.vertices, dtype=np.float64)
        outsideness = _outsideness(points, band_centres, first_axis, second_axis)
        if outsideness is None:
            continue
        if best_outsideness is None or outsideness < best_outsideness:
            best_piece, best_outsideness = piece, outsideness

    if best_piece is None or len(best_piece.faces) < MIN_FACES_AFTER_SELECTION:
        print(f"   band selection: {len(pieces)} pieces, none the bands encircle "
              f"is big enough, keeping all of them")
        return cut

    print(f"   band selection: {len(pieces)} pieces, kept the one the bands "
          f"encircle ({len(best_piece.faces):,} faces), dropped "
          f"{len(pieces) - 1}")
    return best_piece
