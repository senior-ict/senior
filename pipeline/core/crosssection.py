"""Cross-section circumference at the cutting plane, by least-squares ellipse fit.

Stage 6 reports a volume, which says nothing about the shape that produced it.
A circumference at the cut is the one limb dimension that can be checked against
a tape measure without water, so it is measured here and printed alongside.

The slice is taken from `leg.ply`, Stage 3's complete limb, never a cut one:
the cut caps the
exposed cross-section with a synthetic grid (`core/fill.py:cap_points_on_plane`)
that lies on exactly the plane being measured, and fitting to those interior
points pulls the ellipse inward. `leg.ply` is the same cloud levelled and
floor-cut but before the cut and before any capping, so every point in the slab
is reconstructed surface.

Both cloud and plane must be in LEVELLED space, which is why the plane is read
from `cutting_line_review.json` or `cutting_line_levelled.json` and never
`cutting_line.json` — the planes are detected before levelling and the clouds
written after. The review copy wins when it exists: it holds the planes the
measured mesh was actually cut at, which is what a circumference has to describe.
"""
import json
import math
import os

import numpy as np

# Half-thickness of the slice, in real millimetres. 4 mm holds a fully closed
# ring on the captures in hand while staying thin against a ~55 mm limb radius;
# the fitted circumference moves 1.2% across a 1.5-10 mm sweep, so the choice is
# not load-bearing.
SLAB_HALF_MM = 4.0

# How far inside each cut face to take the section, in millimetres. The face
# itself is a flat triangulated cap, so a section taken on it returns the cap
# rather than a ring. Far enough in to clear the cap, near enough that the limb
# has not tapered: on 6_3d_scanner_3c the knee read 31.33 cm at 5 mm and
# 31.54 cm at 10 mm, against the scan's 31.24 cm.
SECTION_INSET_MM = 5.0

# A vertex this far outside the band planes says the mesh was never cut. Stage 5
# publishes the uncut solid under the cut name when the cut fails, and scaling
# from a whole leg because of that would be silent.
UNCUT_TOLERANCE_MM = 10.0
UNCUT_VERTEX_FRACTION = 0.02

# Below this angular coverage the fit is extrapolating across a gap rather than
# interpolating a ring, and the reported number is not a measurement.
MAX_ARC_GAP_DEG = 45.0


def fit_ellipse_direct(x, y):
    """Halir-Flusser direct least-squares ellipse fit.

    Returns conic coefficients (a, b, c, d, e, f) of
    a x^2 + b xy + c y^2 + d x + e y + f = 0, constrained to an ellipse by
    4ac - b^2 = 1.

    This is the numerically stable decomposition of Fitzgibbon's method: the
    design matrix is split into its quadratic and linear halves so the
    generalised eigenproblem is solved on a well-conditioned 3x3 rather than a
    near-singular 6x6. The unsplit form loses the fit outright on data that is
    off-origin and elongated, which a limb cross-section in mesh units is.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()

    D1 = np.stack([x * x, x * y, y * y], axis=1)     # quadratic part
    D2 = np.stack([x, y, np.ones_like(x)], axis=1)   # linear part

    S1 = D1.T @ D1
    S2 = D1.T @ D2
    S3 = D2.T @ D2

    if abs(np.linalg.det(S3)) < 1e-300:
        raise ValueError("slice is degenerate (collinear points) — no ellipse")

    T = -np.linalg.solve(S3, S2.T)
    M = S1 + S2 @ T

    # Pre-multiply by inv(C1) for the ellipse constraint 4ac - b^2 = 1.
    M = np.array([M[2] / 2.0, -M[1], M[0] / 2.0])

    _, evec = np.linalg.eig(M)
    cond = 4.0 * evec[0] * evec[2] - evec[1] ** 2
    idx = np.nonzero(cond > 0)[0]
    if idx.size == 0:
        raise ValueError("no elliptical solution — the slice is not closed")

    a1 = evec[:, idx[0]]
    return np.concatenate([a1, T @ a1])


def ellipse_geometry(coef):
    """Conic coefficients -> (centre, semi-major a, semi-minor b, angle rad).

    Translate to the conic's centre, then diagonalise the quadratic form.
    `a >= b` on return.
    """
    a, b, c, d, e, f = coef
    # The xy coefficient is 'b' in the polynomial but 2B in matrix form.
    B, D, E = b / 2.0, d / 2.0, e / 2.0

    denom = a * c - B * B
    if abs(denom) < 1e-300:
        raise ValueError("degenerate conic — not an ellipse")

    cx = (B * E - c * D) / denom
    cy = (B * D - a * E) / denom
    fc = f + D * cx + E * cy          # constant term once centred

    evals, evecs = np.linalg.eigh(np.array([[a, B], [B, c]], dtype=np.float64))
    with np.errstate(divide="ignore", invalid="ignore"):
        axes_sq = -fc / evals
    if np.any(axes_sq <= 0) or not np.all(np.isfinite(axes_sq)):
        raise ValueError("conic solved to a hyperbola or an imaginary ellipse")

    axes = np.sqrt(axes_sq)
    order = np.argsort(axes)[::-1]     # major first
    major = evecs[:, order[0]]
    return (np.array([cx, cy]), float(axes[order[0]]), float(axes[order[1]]),
            float(math.atan2(major[1], major[0])))


def ramanujan2(a, b):
    """Ramanujan's second approximation to the perimeter of an ellipse.

        P = pi (a + b) (1 + 3h / (10 + sqrt(4 - 3h))),  h = (a-b)^2 / (a+b)^2

    Measured against the exact elliptic integral it is right to 1e-11 at the
    a/b ~ 1.15 a limb cross-section reaches, so its error is many orders below
    the pipeline's ~1-2% surface-noise floor.
    """
    if a + b <= 0:
        raise ValueError("degenerate ellipse")
    h = ((a - b) ** 2) / ((a + b) ** 2)
    return math.pi * (a + b) * (1.0 + (3.0 * h) / (10.0 + math.sqrt(4.0 - 3.0 * h)))


def plane_basis(normal):
    """Orthonormal (u, v, n) with u, v spanning the plane of the given normal."""
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    # Seed against the axis the normal is least aligned with, so the cross
    # product is never taken between near-parallel vectors.
    seed = np.zeros(3)
    seed[int(np.argmin(np.abs(n)))] = 1.0
    u = np.cross(n, seed)
    u /= np.linalg.norm(u)
    return u, np.cross(n, u), n


def fit_slice(points, centroid, normal, linear_scale, slab_half_mm=SLAB_HALF_MM,
              points_already_on_plane=False):
    """Fit one cross-section. Returns a dict of centimetre measurements.

    `linear_scale` is cm per mesh unit, taken from whatever derivation Stage 6
    used, so this reports on exactly the same scale as `volumes.csv`.

    `points_already_on_plane` says the caller has supplied a ring that lies on
    the plane already, as `section_ring` does, so the slab filter would throw
    all of it away. The fit itself is identical either way.
    """
    c = np.asarray(centroid, dtype=np.float64)
    u, v, n = plane_basis(normal)

    if points_already_on_plane:
        slab = np.asarray(points, dtype=np.float64)
    else:
        slab = points[np.abs((points - c) @ n) <= (slab_half_mm / 10.0) / linear_scale]
    if len(slab) < 12:
        raise ValueError(f"only {len(slab)} points in the slab — need 12")

    local = slab - c
    xy = np.stack([local @ u, local @ v], axis=1)

    centre, a_u, b_u, angle = ellipse_geometry(fit_ellipse_direct(xy[:, 0], xy[:, 1]))
    a_cm, b_cm = a_u * linear_scale, b_u * linear_scale

    d = xy - centre
    phi = np.mod(np.arctan2(d[:, 1], d[:, 0]), 2.0 * math.pi)
    r_pt = np.linalg.norm(d, axis=1)

    # Radial residual: how far the points sit from the fitted ellipse along the
    # ray from its centre. Reported because an algebraic fit always returns
    # something, and this is what says whether "ellipse" described the slice.
    th = np.arctan2(d[:, 1], d[:, 0]) - angle
    r_ell = 1.0 / np.sqrt((np.cos(th) / a_u) ** 2 + (np.sin(th) / b_u) ** 2)
    resid_mm = (r_pt - r_ell) * linear_scale * 10.0

    # Angular coverage. A conic fit to a partial arc still returns an ellipse —
    # it extrapolates the missing side, with a *better* residual than the truth.
    # This is the only diagnostic that catches a limb whose back VGGT never
    # reconstructed, so it is checked rather than assumed.
    srt = np.sort(phi)
    gaps = np.diff(np.concatenate([srt, [srt[0] + 2.0 * math.pi]]))
    max_gap_deg = math.degrees(float(gaps.max()))
    coverage = len(np.unique((srt / (2.0 * math.pi) * 72).astype(int) % 72)) / 72.0

    # Independent cross-check: median radius per wedge, joined into a closed
    # polygon. It assumes no shape model, so a large disagreement means the
    # cross-section is not elliptical — not that the fit failed.
    nb = 36
    wedge = (phi / (2.0 * math.pi) * nb).astype(int) % nb
    cen = (np.arange(nb) + 0.5) / nb * 2.0 * math.pi
    keep = [k for k in range(nb) if np.any(wedge == k)]
    rad = np.array([np.median(r_pt[wedge == k]) for k in keep]) * linear_scale
    ring = np.stack([rad * np.cos(cen[keep]), rad * np.sin(cen[keep])], axis=1)
    poly_cm = float(np.sum(np.linalg.norm(
        np.diff(np.vstack([ring, ring[:1]]), axis=0), axis=1)))

    return {
        "a_cm": a_cm,
        "b_cm": b_cm,
        "circumference_cm": ramanujan2(a_cm, b_cm),
        "polygon_circumference_cm": poly_cm,
        "tilt_deg": math.degrees(angle) % 180.0,
        "n_slab": int(len(slab)),
        "coverage": float(coverage),
        "max_gap_deg": max_gap_deg,
        "resid_rms_mm": float(np.sqrt(np.mean(resid_mm ** 2))),
        "partial_arc": bool(max_gap_deg > MAX_ARC_GAP_DEG),
    }


def load_cut_geometry(clean_dir):
    """(points, markers) from a Stage 3 directory, both in levelled space.

    Returns (None, None) with a printed reason when the stage did not leave the
    two artefacts behind — a deferred cut has no planes yet, and that is a
    normal state, not a failure.
    """
    import open3d as o3d

    # The review's planes win when a review happened. Both files are levelled
    # and carry the same shape, but they can disagree: a reviewer who moved,
    # added or removed a plane produced the cut the volumes were computed from,
    # while cutting_line_levelled.json still records what detection proposed.
    # Reading the wrong one reports a circumference at a plane the measured
    # mesh was never cut at — the same precedence the service already uses when
    # it serves cutting_line.json to the review screen.
    debug_dir = os.path.join(clean_dir, "debug")
    review_json = os.path.join(debug_dir, "cutting_line_review.json")
    plane_json = (review_json if os.path.exists(review_json)
                  else os.path.join(debug_dir, "cutting_line_levelled.json"))
    cloud_path = os.path.join(clean_dir, "objects", "leg.ply")

    for p in (plane_json, cloud_path):
        if not os.path.exists(p):
            print(f"  circumference: skipped — no {os.path.basename(p)}")
            return None, None

    with open(plane_json) as fh:
        data = json.load(fh)
    if data.get("space") != "levelled":
        print(f"  circumference: skipped — {plane_json} is not levelled space")
        return None, None

    markers = data.get("markers", [])
    if not markers:
        print("  circumference: skipped — no cutting plane detected")
        return None, None

    pts = np.asarray(o3d.io.read_point_cloud(cloud_path).points, dtype=np.float64)
    if len(pts) == 0:
        print(f"  circumference: skipped — {cloud_path} is empty")
        return None, None
    return pts, markers


def cut_mesh_path(clean_dir):
    """Where Stage 5 leaves the cut limb, given a Stage 3 directory."""
    run_dir = os.path.dirname(os.path.normpath(clean_dir))
    return os.path.join(run_dir, "05_watertight", "mesh", "leg_cut.ply")


def mesh_was_really_cut(mesh, markers):
    """True when the mesh lies between the band planes, so a cut really happened.

    Stage 5 publishes the UNCUT solid under the cut name whenever the cut fails
    or no marker survives, which is deliberate: a rigid object with no band
    still has to get a volume. Scaling from that without noticing would measure
    a whole leg and call it a segment, so it is checked rather than assumed.
    """
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    if len(vertices) == 0:
        return False

    outside = np.zeros(len(vertices), dtype=bool)
    for marker in markers:
        centroid = np.asarray(marker["centroid"], dtype=np.float64)
        normal = np.asarray(marker["normal"], dtype=np.float64)
        normal = normal / (np.linalg.norm(normal) + 1e-8)
        signed = (vertices - centroid) @ normal
        # Only the far side of each plane counts as outside, and which side that
        # is comes from where the rest of the mesh sits.
        if float(np.median(signed)) < 0.0:
            signed = -signed
        outside |= signed < -(UNCUT_TOLERANCE_MM / 10.0)

    return float(outside.mean()) <= UNCUT_VERTEX_FRACTION


def load_cut_mesh_geometry(clean_dir):
    """(mesh, markers) from the Stage 5 cut limb, both in levelled space.

    Returns (None, None) with a printed reason whenever the cut mesh cannot be
    trusted, so the caller can fall back to Stage 3's cloud.
    """
    import trimesh

    _points, markers = load_cut_geometry(clean_dir)
    if markers is None:
        return None, None

    mesh_path = cut_mesh_path(clean_dir)
    if not os.path.exists(mesh_path):
        print(f"  circumference: no {os.path.basename(mesh_path)}, "
              f"falling back to the Stage 3 cloud")
        return None, None

    mesh = trimesh.load(mesh_path, process=False)
    if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
        print("  circumference: the cut mesh has no faces, "
              "falling back to the Stage 3 cloud")
        return None, None

    if not mesh_was_really_cut(mesh, markers):
        print("  circumference: leg_cut.ply reaches past the band planes, so the "
              "cut did not happen — falling back to the Stage 3 cloud")
        return None, None

    return mesh, markers


def section_ring(mesh, centroid, normal, linear_scale,
                 inset_mm=SECTION_INSET_MM):
    """The limb's outline where a plane crosses it, taken a little inside the face.

    Cuts the plane against every triangle it crosses, so the points come back on
    the surface and on the plane however the mesher happened to place vertices.
    A slab of nearby vertices cannot promise either: on these meshes it returned
    between 0 and 33 points where this returns a few hundred.

    The section is taken `inset_mm` inside the cut face. On the face itself the
    mesh is a flat cap, and a section of a cap is a disc rather than a ring.

    When the plane crosses more than one piece, the piece the band is tied round
    is the one whose outline the band centre falls inside — the same rule the
    cut itself uses.

    Returns an (N, 3) array, or None when no outline could be taken.
    """
    centroid = np.asarray(centroid, dtype=np.float64)
    unit_normal = np.asarray(normal, dtype=np.float64)
    unit_normal = unit_normal / (np.linalg.norm(unit_normal) + 1e-8)

    # Step inward, towards the body of the mesh rather than out through the face.
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    if float(np.median((vertices - centroid) @ unit_normal)) < 0.0:
        unit_normal = -unit_normal
    origin = centroid + unit_normal * ((inset_mm / 10.0) / linear_scale)

    section = mesh.section(plane_origin=origin, plane_normal=unit_normal)
    if section is None:
        return None

    loops = [np.asarray(loop, dtype=np.float64) for loop in section.discrete
             if len(loop) >= 12]
    if not loops:
        return None
    if len(loops) == 1:
        return loops[0]

    first_axis, second_axis, _ = plane_basis(unit_normal)
    flat_centre = np.array([centroid @ first_axis, centroid @ second_axis])

    best_loop = None
    best_outsideness = None
    for loop in loops:
        flattened = np.column_stack([loop @ first_axis, loop @ second_axis])
        outsideness = _how_far_outside(flattened, flat_centre)
        if outsideness is None:
            continue
        if best_outsideness is None or outsideness < best_outsideness:
            best_loop, best_outsideness = loop, outsideness
    return best_loop if best_loop is not None else loops[0]


def _how_far_outside(outline_points, probe_point):
    """How far outside an outline a point falls, negative when it is inside."""
    try:
        from scipy.spatial import ConvexHull, QhullError
    except ImportError:
        return None
    if len(outline_points) < 3:
        return None
    try:
        hull = ConvexHull(outline_points)
    except QhullError:
        return None
    signed = hull.equations[:, :2] @ probe_point + hull.equations[:, 2]
    return float(signed.max())


def report_cut_circumference(clean_dir, linear_scale, slab_half_mm=SLAB_HALF_MM):
    """Print the circumference at each cutting plane. Returns a list of results.

    Never raises: a failed fit must not cost a run its volumes. Every failure
    path prints its reason — a silent one here would be the exact defect class
    `docs/reviews/repo_review.md` swept for.
    """
    try:
        mesh, markers = load_cut_mesh_geometry(clean_dir)
    except Exception as exc:
        print(f"  circumference: the cut mesh would not load — "
              f"{type(exc).__name__}: {exc}")
        mesh, markers = None, None

    pts = None
    if mesh is None:
        try:
            pts, markers = load_cut_geometry(clean_dir)
        except Exception as exc:
            print(f"  circumference: skipped — {type(exc).__name__}: {exc}")
            return []
        if pts is None:
            return []

    if mesh is not None:
        print(f"\n  Circumference at the cutting plane "
              f"(least-squares ellipse, Ramanujan II, section of the cut mesh "
              f"{SECTION_INSET_MM:.0f} mm inside each face):")
        print("      note: a watertight mesh always sections to a closed loop, "
              "so ring coverage reads 100% here and cannot catch a limb whose "
              "back was never reconstructed. Stage 3's cloud is where that shows.")
    else:
        print(f"\n  Circumference at the cutting plane "
              f"(least-squares ellipse, Ramanujan II, slab ±{slab_half_mm:.0f} mm):")

    out = []
    for i, mk in enumerate(markers):
        try:
            if mesh is not None:
                ring = section_ring(mesh, mk["centroid"], mk["normal"],
                                    linear_scale)
                if ring is None:
                    print(f"    plane {i}: FAILED — the plane took no outline "
                          f"from the cut mesh")
                    continue
                r = fit_slice(ring, mk["centroid"], mk["normal"], linear_scale,
                              slab_half_mm, points_already_on_plane=True)
            else:
                r = fit_slice(pts, mk["centroid"], mk["normal"], linear_scale,
                              slab_half_mm)
        except Exception as exc:
            print(f"    plane {i}: FAILED — {type(exc).__name__}: {exc}")
            continue

        label = f"plane {i}" if len(markers) > 1 else "cut"
        print(f"    {label}: CIRCUMFERENCE = {r['circumference_cm']:.2f} cm"
              f"   (a = {r['a_cm']:.2f} cm, b = {r['b_cm']:.2f} cm,"
              f" a/b = {r['a_cm'] / r['b_cm']:.2f})")
        print(f"      {r['n_slab']} slab pts, {r['coverage'] * 100:.0f}% ring coverage, "
              f"residual RMS {r['resid_rms_mm']:.2f} mm, "
              f"polygon cross-check {r['polygon_circumference_cm']:.2f} cm "
              f"({(r['circumference_cm'] - r['polygon_circumference_cm']) / r['polygon_circumference_cm'] * 100:+.1f}%)")
        if r["partial_arc"]:
            print(f"      ** WARNING: largest gap {r['max_gap_deg']:.0f}° — the ring is "
                  f"open and the fit is extrapolating across it. Not a measurement. **")
        r["plane"] = i
        out.append(r)
    return out
