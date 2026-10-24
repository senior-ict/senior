"""Circumference of the leg at a cutting plane, by least-squares ellipse fit.

Stage 7 reports a volume, which says nothing about the shape that produced it.
A circumference at the cut is the one limb dimension that can be checked
against a tape measure without water, so it is measured here and printed
beside the volumes.

Two things decide whether the number means anything:

  which cloud    The slice is taken from the UNCUT `clean_objects/obj.ply`,
                 never `segmented/segmented_obj.ply`. The cut removes
                 everything past the plane, so a slab centred on that plane
                 would hold only the points on one side of it and the fitted
                 ellipse would describe half a ring.
  which space    The cloud and the planes must share a coordinate frame.
                 Stage 3 levels the scene before clustering, and the marker
                 planes are fitted on that same levelled cloud, so both are in
                 levelled space and no extra transform is needed.

The fit is an algebraic one and always returns an ellipse, including for a
half-reconstructed limb where it quietly extrapolates across the missing side.
Angular coverage is therefore measured and reported with every result, and a
gap wider than MAX_ARC_GAP_DEGREES is called out as not a measurement.
"""
import json
import math
import os

import numpy as np

# Half-thickness of the slice, in real millimetres. 4 mm holds a closed ring
# while staying thin against a limb radius of roughly 55 mm.
SLAB_HALF_MILLIMETRES = 4.0

# Below this angular coverage the fit is extrapolating across a gap rather
# than interpolating a ring, and the reported number is not a measurement.
MAX_ARC_GAP_DEGREES = 45.0

# Fewest points that can support a six-coefficient conic fit with any margin.
MINIMUM_SLAB_POINTS = 12

# Wedges used by the polygon cross-check, and by the coverage figure.
POLYGON_WEDGE_COUNT = 36
COVERAGE_WEDGE_COUNT = 72


def fit_ellipse_direct(x_values, y_values):
    """Halir-Flusser direct least-squares ellipse fit.

    Returns the conic coefficients (a, b, c, d, e, f) of
    a*x^2 + b*x*y + c*y^2 + d*x + e*y + f = 0, constrained to an ellipse by
    4ac - b^2 = 1.

    This is the numerically stable form of Fitzgibbon's method: the design
    matrix is split into its quadratic and linear halves so the generalised
    eigenproblem is solved on a well-conditioned 3x3 instead of a nearly
    singular 6x6. The unsplit form loses the fit outright on data that is
    off-origin and elongated, which a limb cross-section in mesh units is.
    """
    x_values = np.asarray(x_values, dtype=np.float64).ravel()
    y_values = np.asarray(y_values, dtype=np.float64).ravel()

    quadratic_design = np.stack(
        [x_values * x_values, x_values * y_values, y_values * y_values], axis=1)
    linear_design = np.stack(
        [x_values, y_values, np.ones_like(x_values)], axis=1)

    scatter_quadratic = quadratic_design.T @ quadratic_design
    scatter_cross = quadratic_design.T @ linear_design
    scatter_linear = linear_design.T @ linear_design

    if abs(np.linalg.det(scatter_linear)) < 1e-300:
        raise ValueError("slice is degenerate (collinear points) — no ellipse")

    # Eliminate the linear coefficients, leaving a 3x3 problem in the
    # quadratic ones alone.
    linear_from_quadratic = -np.linalg.solve(scatter_linear, scatter_cross.T)
    reduced = scatter_quadratic + scatter_cross @ linear_from_quadratic

    # Pre-multiply by the inverse of the constraint matrix for 4ac - b^2 = 1.
    reduced = np.array([reduced[2] / 2.0, -reduced[1], reduced[0] / 2.0])

    _, eigenvectors = np.linalg.eig(reduced)
    ellipse_condition = (4.0 * eigenvectors[0] * eigenvectors[2]
                         - eigenvectors[1] ** 2)
    elliptical_columns = np.nonzero(ellipse_condition > 0)[0]
    if elliptical_columns.size == 0:
        raise ValueError("no elliptical solution — the slice is not closed")

    quadratic_coefficients = eigenvectors[:, elliptical_columns[0]]
    linear_coefficients = linear_from_quadratic @ quadratic_coefficients
    return np.concatenate([quadratic_coefficients, linear_coefficients])


def ellipse_geometry(coefficients):
    """Conic coefficients to (centre, semi-major, semi-minor, angle in radians).

    Translates the conic to its own centre, then diagonalises the quadratic
    form. The semi-major axis is always the first of the two returned.
    """
    (x_squared_coefficient, cross_term_coefficient, y_squared_coefficient,
     x_coefficient, y_coefficient, constant_coefficient) = coefficients
    # The cross term appears as b in the polynomial but as b/2 in matrix form,
    # and the same halving applies to the two linear terms.
    half_cross_term = cross_term_coefficient / 2.0
    half_x_coefficient = x_coefficient / 2.0
    half_y_coefficient = y_coefficient / 2.0

    denominator = (x_squared_coefficient * y_squared_coefficient
                   - half_cross_term * half_cross_term)
    if abs(denominator) < 1e-300:
        raise ValueError("degenerate conic — not an ellipse")

    centre_x = (half_cross_term * half_y_coefficient
                - y_squared_coefficient * half_x_coefficient) / denominator
    centre_y = (half_cross_term * half_x_coefficient
                - x_squared_coefficient * half_y_coefficient) / denominator
    constant_at_centre = (constant_coefficient
                          + half_x_coefficient * centre_x
                          + half_y_coefficient * centre_y)

    quadratic_form = np.array(
        [[x_squared_coefficient, half_cross_term],
         [half_cross_term, y_squared_coefficient]], dtype=np.float64)
    eigenvalues, eigenvectors = np.linalg.eigh(quadratic_form)
    with np.errstate(divide="ignore", invalid="ignore"):
        axes_squared = -constant_at_centre / eigenvalues
    if np.any(axes_squared <= 0) or not np.all(np.isfinite(axes_squared)):
        raise ValueError("conic solved to a hyperbola or an imaginary ellipse")

    axes = np.sqrt(axes_squared)
    order = np.argsort(axes)[::-1]
    major_direction = eigenvectors[:, order[0]]
    centre = np.array([centre_x, centre_y])
    angle = float(math.atan2(major_direction[1], major_direction[0]))
    return centre, float(axes[order[0]]), float(axes[order[1]]), angle


def ellipse_perimeter(semi_major, semi_minor):
    """Ramanujan's second approximation to the perimeter of an ellipse.

        P = pi * (a + b) * (1 + 3h / (10 + sqrt(4 - 3h))),
        h = (a - b)^2 / (a + b)^2

    Against the exact elliptic integral this is correct to about 1e-11 at the
    axis ratio a limb cross-section reaches, far below the pipeline's own
    surface-noise floor.
    """
    if semi_major + semi_minor <= 0:
        raise ValueError("degenerate ellipse")
    axis_difference = (semi_major - semi_minor) ** 2
    axis_sum = (semi_major + semi_minor) ** 2
    shape_term = axis_difference / axis_sum
    correction = (3.0 * shape_term) / (10.0 + math.sqrt(4.0 - 3.0 * shape_term))
    return math.pi * (semi_major + semi_minor) * (1.0 + correction)


def plane_basis(normal):
    """Orthonormal (first_axis, second_axis, normal) spanning the given plane."""
    unit_normal = np.asarray(normal, dtype=np.float64)
    unit_normal = unit_normal / np.linalg.norm(unit_normal)
    # Seed against the axis the normal is least aligned with, so the cross
    # product is never taken between two nearly parallel vectors.
    seed = np.zeros(3)
    seed[int(np.argmin(np.abs(unit_normal)))] = 1.0
    first_axis = np.cross(unit_normal, seed)
    first_axis = first_axis / np.linalg.norm(first_axis)
    second_axis = np.cross(unit_normal, first_axis)
    return first_axis, second_axis, unit_normal


def polygon_perimeter_centimetres(angles, radii, centimetres_per_unit):
    """Perimeter of a closed polygon built from the median radius per wedge.

    This assumes no shape model at all, so a large disagreement with the
    fitted ellipse means the cross-section is not elliptical — it does not
    mean the fit failed.
    """
    wedge_of_point = (angles / (2.0 * math.pi) * POLYGON_WEDGE_COUNT)
    wedge_of_point = wedge_of_point.astype(int) % POLYGON_WEDGE_COUNT

    corner_positions = []
    for wedge in range(POLYGON_WEDGE_COUNT):
        in_this_wedge = wedge_of_point == wedge
        if not np.any(in_this_wedge):
            continue
        wedge_centre_angle = ((wedge + 0.5) / POLYGON_WEDGE_COUNT
                              * 2.0 * math.pi)
        median_radius = float(np.median(radii[in_this_wedge]))
        radius_centimetres = median_radius * centimetres_per_unit
        corner_positions.append([radius_centimetres * math.cos(wedge_centre_angle),
                                 radius_centimetres * math.sin(wedge_centre_angle)])

    if len(corner_positions) < 3:
        return float("nan")

    corners = np.array(corner_positions)
    closed = np.vstack([corners, corners[:1]])
    edge_lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    return float(np.sum(edge_lengths))


def fit_slice(points, centroid, normal, centimetres_per_unit,
              slab_half_millimetres=SLAB_HALF_MILLIMETRES):
    """Fit one cross-section. Returns a dictionary of centimetre measurements.

    `centimetres_per_unit` is the linear scale Stage 7 derived from the
    reference cube, so the circumference is reported on exactly the same scale
    as the volumes beside it.
    """
    plane_centroid = np.asarray(centroid, dtype=np.float64)
    first_axis, second_axis, unit_normal = plane_basis(normal)

    slab_half_units = (slab_half_millimetres / 10.0) / centimetres_per_unit
    distance_to_plane = (points - plane_centroid) @ unit_normal
    slab = points[np.abs(distance_to_plane) <= slab_half_units]
    if len(slab) < MINIMUM_SLAB_POINTS:
        raise ValueError(f"only {len(slab)} points in the slab — "
                         f"need {MINIMUM_SLAB_POINTS}")

    local = slab - plane_centroid
    in_plane = np.stack([local @ first_axis, local @ second_axis], axis=1)

    coefficients = fit_ellipse_direct(in_plane[:, 0], in_plane[:, 1])
    centre, semi_major_units, semi_minor_units, angle = ellipse_geometry(coefficients)
    semi_major_centimetres = semi_major_units * centimetres_per_unit
    semi_minor_centimetres = semi_minor_units * centimetres_per_unit

    from_centre = in_plane - centre
    angles = np.mod(np.arctan2(from_centre[:, 1], from_centre[:, 0]),
                    2.0 * math.pi)
    point_radii = np.linalg.norm(from_centre, axis=1)

    # Radial residual: how far each point sits from the fitted ellipse along
    # the ray out of its centre. Reported because an algebraic fit always
    # returns something, and this is what says whether "ellipse" described
    # the slice at all.
    angle_from_major = np.arctan2(from_centre[:, 1], from_centre[:, 0]) - angle
    ellipse_radii = 1.0 / np.sqrt(
        (np.cos(angle_from_major) / semi_major_units) ** 2
        + (np.sin(angle_from_major) / semi_minor_units) ** 2)
    residual_millimetres = ((point_radii - ellipse_radii)
                            * centimetres_per_unit * 10.0)

    # Angular coverage. A conic fit to a partial arc still returns an ellipse,
    # extrapolating the missing side with a BETTER residual than the truth, so
    # this is the only diagnostic that catches a limb whose back was never
    # reconstructed.
    sorted_angles = np.sort(angles)
    wrapped = np.concatenate([sorted_angles, [sorted_angles[0] + 2.0 * math.pi]])
    largest_gap_degrees = math.degrees(float(np.diff(wrapped).max()))

    occupied_wedges = (sorted_angles / (2.0 * math.pi) * COVERAGE_WEDGE_COUNT)
    occupied_wedges = occupied_wedges.astype(int) % COVERAGE_WEDGE_COUNT
    coverage = len(np.unique(occupied_wedges)) / COVERAGE_WEDGE_COUNT

    polygon_centimetres = polygon_perimeter_centimetres(
        angles, point_radii, centimetres_per_unit)

    return {
        "semi_major_cm": semi_major_centimetres,
        "semi_minor_cm": semi_minor_centimetres,
        "circumference_cm": ellipse_perimeter(semi_major_centimetres,
                                              semi_minor_centimetres),
        "polygon_circumference_cm": polygon_centimetres,
        "tilt_deg": math.degrees(angle) % 180.0,
        "n_slab": int(len(slab)),
        "coverage": float(coverage),
        "max_gap_deg": largest_gap_degrees,
        "resid_rms_mm": float(np.sqrt(np.mean(residual_millimetres ** 2))),
        "partial_arc": bool(largest_gap_degrees > MAX_ARC_GAP_DEGREES),
    }


def load_cut_geometry(output_dir):
    """(points, planes) for this run, both in levelled space.

    Returns (None, None) with a printed reason when Stage 3 left no planes
    behind. A run with no markers detected has nothing to measure at, and
    that is a normal state rather than a failure.
    """
    import open3d as o3d

    planes_path = os.path.join(output_dir, "segmented", "cut_planes.json")
    cloud_path = os.path.join(output_dir, "clean_objects", "obj.ply")

    for required_path in (planes_path, cloud_path):
        if not os.path.exists(required_path):
            print(f"  circumference: skipped — "
                  f"no {os.path.basename(required_path)}")
            return None, None

    with open(planes_path) as handle:
        data = json.load(handle)
    if data.get("space") != "levelled":
        print(f"  circumference: skipped — {planes_path} is not levelled space")
        return None, None

    planes = data.get("planes", [])
    if not planes:
        print("  circumference: skipped — no cutting plane detected")
        return None, None

    cloud = o3d.io.read_point_cloud(cloud_path)
    points = np.asarray(cloud.points, dtype=np.float64)
    if len(points) == 0:
        print(f"  circumference: skipped — {cloud_path} is empty")
        return None, None
    return points, planes


def report_cut_circumference(output_dir, centimetres_per_unit,
                             slab_half_millimetres=SLAB_HALF_MILLIMETRES):
    """Print the circumference at each cutting plane. Returns a list of results.

    Never raises: a failed fit must not cost a run its volumes. Every failure
    path prints the reason it took, because a silent skip here would look
    exactly like a run that had no bands.
    """
    try:
        points, planes = load_cut_geometry(output_dir)
    except Exception as error:
        print(f"  circumference: skipped — {type(error).__name__}: {error}")
        return []
    if points is None:
        return []

    print(f"\n  Circumference at the cutting plane "
          f"(least-squares ellipse, Ramanujan II, "
          f"slab +/-{slab_half_millimetres:.0f} mm):")

    results = []
    for plane_index in range(len(planes)):
        plane = planes[plane_index]
        label = plane.get("label", f"plane {plane_index}")
        try:
            measurement = fit_slice(points, plane["centroid"], plane["normal"],
                                    centimetres_per_unit, slab_half_millimetres)
        except Exception as error:
            print(f"    {label}: FAILED — {type(error).__name__}: {error}")
            continue

        axis_ratio = measurement["semi_major_cm"] / measurement["semi_minor_cm"]
        print(f"    {label}: CIRCUMFERENCE = "
              f"{measurement['circumference_cm']:.2f} cm"
              f"   (a = {measurement['semi_major_cm']:.2f} cm,"
              f" b = {measurement['semi_minor_cm']:.2f} cm,"
              f" a/b = {axis_ratio:.2f})")

        polygon = measurement["polygon_circumference_cm"]
        if polygon > 0:
            polygon_difference = (100.0 * (measurement["circumference_cm"] - polygon)
                                  / polygon)
            polygon_text = f"{polygon:.2f} cm ({polygon_difference:+.1f}%)"
        else:
            polygon_text = "unavailable"
        print(f"      {measurement['n_slab']} slab pts, "
              f"{measurement['coverage'] * 100:.0f}% ring coverage, "
              f"residual RMS {measurement['resid_rms_mm']:.2f} mm, "
              f"polygon cross-check {polygon_text}")

        if measurement["partial_arc"]:
            print(f"      ** WARNING: largest gap "
                  f"{measurement['max_gap_deg']:.0f} deg — the ring is open "
                  f"and the fit is extrapolating across it. "
                  f"Not a measurement. **")

        measurement["label"] = label
        results.append(measurement)
    return results
