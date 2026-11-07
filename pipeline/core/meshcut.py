"""Apply the confirmed marker planes to a watertight mesh.

This is the mesh counterpart of `core/segmentation.py:apply_marker_cut`, which
does the same job on a point cloud. The rule is identical and stated the same
way, in terms of above and below rather than sides:

    0 markers -> no cut
    1 marker  -> keep what is BELOW the plane
    2 markers -> keep what lies BETWEEN the two planes

Slicing leaves everything in the slab, which on a bent leg can include another
body part passing through it. So one rule is added on top of the shared three,
and it has no counterpart in the cloud path: of the solids the cut leaves, keep
the one the bands are tied round, judged in plan view with height ignored. The
planes cannot make that call, since the stray piece shares their z range exactly.

Cutting the solid rather than the cloud is what lets a clinician place the cut
on a surface instead of a scatter of points. It also removes the reconstruction
step that used to sit between the cut and the measurement: the cloud cut had to
cap the exposed cross-section and then hand it to Poisson, which reconstructs
that flat face along with everything else. Slicing a closed mesh produces the
face directly, and nothing runs after it that could round it off.

The input must be watertight. A plane cut caps cleanly only when the
cross-section is a closed loop, which an open surface cannot guarantee -- on a
Stage 4 mesh the cap collapsed to a single triangle, and the result stayed
non-manifold (euler -9 before, -8 after). Stage 5's repaired mesh goes in
watertight with euler 2 and comes out the same way, which is what Stage 6's
exact signed-volume method requires.
"""
import numpy as np

# A limb segment is bounded by at most two cuts. A third plane can only
# contradict one of them, so extra planes are dropped rather than combined.
MAX_MARKERS = 2

# Below this the plane stands vertical and has no above or below, so the
# above/below rule is undefined and the plane is skipped instead of guessed at.
MIN_VERTICAL_COMPONENT = 1e-3

# A cut that leaves almost nothing behind is a failed cut, not a small limb.
# Matches the cloud path's floor of 50 points.
MIN_FACES_AFTER_CUT = 50

# A piece the bands do not encircle is kept anyway if dropping it would leave
# almost nothing, on the same reasoning as MIN_FACES_AFTER_CUT: a selection that
# throws away the limb is a failed selection, not a tiny limb.
MIN_FACES_AFTER_SELECTION = 50


def _upward_plane(marker, up_axis):
    """Returns one marker as (origin, upward normal), or None if it stands vertical.

    The detected normal may point either way, so it is flipped to point along
    `up_axis`. That makes the sign of the detection irrelevant to the outcome, which
    is what lets a reviewer drag a plane without inverting the selection.
    """
    origin = np.asarray(marker["centroid"], dtype=np.float64)
    normal = np.asarray(marker["normal"], dtype=np.float64)
    normal = normal / (np.linalg.norm(normal) + 1e-8)

    vertical_component = float(np.dot(normal, up_axis))
    if abs(vertical_component) < MIN_VERTICAL_COMPONENT:
        return None
    if vertical_component < 0:
        normal = -normal
    return origin, normal


def _slice_keeping(mesh, origin, normal):
    """Slices the mesh at the plane, keeping the side the normal points toward.

    Returns None when the cut removes everything.
    """
    sliced = mesh.slice_plane(plane_origin=origin, plane_normal=normal, cap=True)
    if sliced is None or len(sliced.faces) == 0:
        return None
    sliced.merge_vertices()
    return sliced


def _restore_vertex_colours(cut_mesh, source_mesh):
    """Copies the source mesh's vertex colours onto the cut one, by nearest vertex.

    `slice_plane` builds new geometry and drops the visual data, so a cut limb
    comes out flat grey -- which is what the result screen was showing next to a
    volume measured from it. Every vertex the cut kept sits exactly where it did
    before, so a nearest-vertex lookup returns its own colour unchanged; only the
    cap is new, and its vertices take the colour of the rim they were cut from.
    That is the same thing the point-cloud path did when it capped a cut.
    """
    source_colours = getattr(source_mesh.visual, "vertex_colors", None)
    if source_colours is None or len(source_colours) == 0:
        return cut_mesh

    source_points = np.asarray(source_mesh.vertices, dtype=np.float64)
    cut_points = np.asarray(cut_mesh.vertices, dtype=np.float64)

    try:
        from scipy.spatial import cKDTree

        _distances, nearest = cKDTree(source_points).query(cut_points)
    except ImportError:
        # Without scipy, fall back to a chunked brute-force search. Slower, but
        # a limb mesh is tens of thousands of vertices, not millions.
        nearest = np.empty(len(cut_points), dtype=np.int64)
        chunk_size = 2048
        for start in range(0, len(cut_points), chunk_size):
            chunk = cut_points[start:start + chunk_size]
            distances = np.linalg.norm(
                chunk[:, None, :] - source_points[None, :, :], axis=2)
            nearest[start:start + chunk_size] = distances.argmin(axis=1)

    cut_mesh.visual.vertex_colors = np.asarray(source_colours)[nearest]
    return cut_mesh


def _plan_view_outsideness(component, band_centres):
    """How far outside a piece's plan-view outline the band centres fall, in units.

    Measured in x and y only, with height thrown away on purpose. The two cut
    planes have already fixed the z range, so the limb and any other body part
    passing through the slab share that range exactly and height cannot tell them
    apart. Plan view can: the bands are tied round the limb, so the limb is the
    piece whose outline the band centres sit inside.

    Returns the largest signed distance over the two centres, which is negative
    when every centre lies inside the outline. Returns None when the piece has no
    usable outline, which is treated as "not the limb" by the caller.
    """
    try:
        from scipy.spatial import ConvexHull, QhullError
    except ImportError:
        return None

    flattened = np.asarray(component.vertices, dtype=np.float64)[:, :2]
    if len(flattened) < 3:
        return None
    try:
        outline = ConvexHull(flattened)
    except QhullError:
        return None

    # scipy writes each edge as normal . point + offset <= 0 for points inside,
    # so the largest value over all edges is negative exactly when the point is
    # inside, and grows with how far outside it is.
    worst_distance = -np.inf
    for centre in band_centres:
        signed_distances = outline.equations[:, :2] @ centre + outline.equations[:, 2]
        worst_distance = max(worst_distance, float(signed_distances.max()))
    return worst_distance


def _keep_the_piece_the_bands_encircle(cut, planes):
    """Of the solids the cut left behind, keep the one the bands are tied round.

    Slicing between two planes keeps everything in the slab, which on a bent leg
    includes whatever else passes through it -- on one capture a 144.8 cm3 flake
    of thigh, sitting 22.8 cm away from the bands in plan view, which Stage 6 was
    summing into the limb volume. The planes cannot exclude it, because it shares
    their z range. The bands can, because they are tied round the limb and
    nothing else.

    A single-piece cut is returned untouched, which is every capture measured so
    far except that one.
    """
    pieces = cut.split(only_watertight=False)
    if len(pieces) < 2:
        return cut

    band_centres = [origin[:2] for origin, _normal in planes]

    best_piece = None
    best_outsideness = None
    for piece in pieces:
        outsideness = _plan_view_outsideness(piece, band_centres)
        if outsideness is None:
            continue
        if best_outsideness is None or outsideness < best_outsideness:
            best_piece, best_outsideness = piece, outsideness

    if best_piece is None or len(best_piece.faces) < MIN_FACES_AFTER_SELECTION:
        print(f"  Band selection: {len(pieces)} pieces, but none the bands "
              f"encircle is big enough -- keeping all of them")
        return cut

    dropped = len(pieces) - 1
    inside = "inside" if best_outsideness <= 0 else f"{best_outsideness:.4f} outside"
    print(f"  Band selection: kept the piece the bands sit {inside} of, "
          f"dropped {dropped} other piece(s)")
    return best_piece


def apply_marker_cut_to_mesh(mesh, markers, up_axis=(0.0, 0.0, 1.0)):
    """Cuts a watertight mesh against at most two marker planes, by height.

    Expects the mesh in levelled space, where `up_axis` is the vertical axis, and the
    markers as {"centroid", "normal"} in that same space.

    Args:
        mesh: a watertight trimesh.Trimesh in levelled space.
        markers: list of {"centroid": (3,), "normal": (3,)}. Normals may point
            either way.
        up_axis: unit vertical axis of the mesh.

    Returns:
        (cut_mesh, case_label). The mesh is returned uncut, with a label saying
        why, whenever the cut cannot be made or would leave almost nothing.
    """
    if len(markers) == 0:
        return mesh, "no_markers"

    up_axis = np.asarray(up_axis, dtype=np.float64)
    up_axis = up_axis / (np.linalg.norm(up_axis) + 1e-8)

    planes = []
    for marker in markers[:MAX_MARKERS]:
        plane = _upward_plane(marker, up_axis)
        if plane is not None:
            planes.append(plane)

    if not planes:
        return mesh, "no_usable_markers"

    if len(planes) == 1:
        # Keep what is BELOW the plane, so the kept side is the one the
        # downward normal points toward.
        origin, normal = planes[0]
        cut = _slice_keeping(mesh, origin, -normal)
        case = "case_1_below"
    else:
        # Keep what lies BETWEEN the two. Which plane is upper is decided by
        # each point's own signed distance in the cloud path; on a mesh the same
        # thing is achieved by keeping below one and above the other, applied in
        # turn. Ordering the planes by height first means the two slices cannot
        # both discard the same side and leave nothing.
        first, second = planes
        first_height = float(np.dot(first[0], up_axis))
        second_height = float(np.dot(second[0], up_axis))
        if first_height <= second_height:
            lower_plane, upper_plane = first, second
        else:
            lower_plane, upper_plane = second, first

        cut = _slice_keeping(mesh, lower_plane[0], lower_plane[1])
        if cut is not None:
            cut = _slice_keeping(cut, upper_plane[0], -upper_plane[1])
        case = "case_2_between"

    if cut is None or len(cut.faces) < MIN_FACES_AFTER_CUT:
        return mesh, "too_few_after_cut"

    cut = _keep_the_piece_the_bands_encircle(cut, planes)

    cut = _restore_vertex_colours(cut, mesh)
    return cut, case
