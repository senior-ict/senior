"""Hold each limb cross-section to a smooth curve around a skeleton, and fill its gaps.

The limb's cleaned cloud still has flaws that Poisson turns into wrong shape:

  - outer defects: stray points at the silhouette edge, where a camera sees
    the skin side-on, stick out from the surface as a spur or bulge;
  - inner defects: a patch sunk inside the surface, a dent;
  - gaps: an arc that no frame reconstructed cleanly is missing, and Poisson
    bridges it with a flat patch (test6 near the upper band, 2026-09-21).

The limb is treated as a tube around a skeleton. It is cut into thin
horizontal slices between the two bands. Each slice gets a centre from a
circle fit (a centroid would be pulled toward whichever side has more
points); the centres are smoothed along the height to make the skeleton.

Around that centre each point has an angle and a radius. One smooth curve is
fitted to the whole slice: radius as a short Fourier series in the angle, with
the higher waves damped so the curve can be oval or have a flat face but not a
kink. The fit uses the slice's points and those of the slices just above and
below, and is repeated with the far-off points left out, so a spur cannot drag
the curve toward itself.

Each point further from the curve than a small tolerance is then classed:
outside the curve is an outer defect and is moved in; inside is an inner
defect and is moved out; either way only as far as the tolerance, so real
texture that shares the curve's shape is left alone. An empty arc is filled
with points on the curve itself, not interpolated from the gap's two ends,
which are often the curled edge points.

It runs after the stacked MLS passes, in levelled space (height is +Z).
"""
import numpy as np

HARMONIC_COUNT = 6                   # waves in the radius curve: oval, flat faces, no kinks
HARMONIC_DAMPING = 0.002             # ridge weight, grows as the wave number to the fourth power
FIT_ROUNDS = 3                       # refits, each leaving out the points far from the last curve
OUTLIER_SPREAD_MULTIPLE = 2.5        # "far" is this many robust spreads from the curve
SLICES_BETWEEN_BANDS = 60            # about 0.5 cm on a 30 cm segment
NEIGHBOUR_SLICES = 1                 # the curve is fitted to this many slices above and below as well
BAND_MARGIN_FRACTION = 0.08          # also treat a little beyond each band
SKELETON_SMOOTHING_SLICES = 5        # moving median over this many slice centres
RADIUS_TOLERANCE_FRACTION = 0.02     # a point may sit 2% of the radius off the curve
ANGLE_BIN_COUNT = 72                 # 5-degree bins, used only to find empty arcs
LARGEST_GAP_TO_FILL_BINS = 24        # fill gaps up to 120 degrees; wider ones are left alone
MINIMUM_POINTS_PER_SLICE = 30


def fit_circle_centre(xy_points):
    """Centre of the least-squares circle through 2-D points (Kasa fit)."""
    x_values = xy_points[:, 0]
    y_values = xy_points[:, 1]
    design = np.column_stack([x_values, y_values, np.ones(len(x_values))])
    target = x_values ** 2 + y_values ** 2
    solution, _, _, _ = np.linalg.lstsq(design, target, rcond=None)
    centre_x = solution[0] / 2.0
    centre_y = solution[1] / 2.0
    return np.array([centre_x, centre_y])


def moving_median(values, window):
    """Median of each row's window of neighbouring rows, for an (N, 2) array; rows that are NaN are ignored."""
    half_window = window // 2
    smoothed = np.full_like(values, np.nan)
    for index in range(len(values)):
        start = max(0, index - half_window)
        end = min(len(values), index + half_window + 1)
        window_values = values[start:end]
        valid_rows = ~np.isnan(window_values).any(axis=1)
        if valid_rows.any():
            smoothed[index] = np.median(window_values[valid_rows], axis=0)
    return smoothed


def fourier_columns(angles):
    """Design matrix for radius = a0 + sum over k of (a_k cos k*angle + b_k sin k*angle)."""
    columns = [np.ones(len(angles))]
    for wave_number in range(1, HARMONIC_COUNT + 1):
        columns.append(np.cos(wave_number * angles))
        columns.append(np.sin(wave_number * angles))
    return np.column_stack(columns)


def damping_weights():
    """Ridge weight per coefficient: none on the mean radius, rising steeply with the wave number."""
    weights = [0.0]
    for wave_number in range(1, HARMONIC_COUNT + 1):
        weight = HARMONIC_DAMPING * float(wave_number) ** 4
        weights.append(weight)
        weights.append(weight)
    return np.array(weights)


def fit_smooth_curve(angles, radii):
    """Coefficients of the smooth radius curve, refitted without far-off points each round."""
    kept = np.ones(len(angles), dtype=bool)
    penalty = np.diag(damping_weights())
    coefficients = None
    for _ in range(FIT_ROUNDS):
        design = fourier_columns(angles[kept])
        normal_matrix = design.T @ design / kept.sum() + penalty
        right_side = design.T @ radii[kept] / kept.sum()
        coefficients = np.linalg.solve(normal_matrix, right_side)
        residuals = radii - fourier_columns(angles) @ coefficients
        median_residual = np.median(residuals[kept])
        robust_spread = 1.4826 * np.median(np.abs(residuals[kept] - median_residual))
        if robust_spread <= 0:
            break
        kept = np.abs(residuals - median_residual) <= OUTLIER_SPREAD_MULTIPLE * robust_spread
    return coefficients


def curve_radius(coefficients, angles):
    """Radius of the fitted curve at these angles."""
    return fourier_columns(np.atleast_1d(angles)) @ coefficients


def empty_arcs(angles):
    """List of (start_bin, length) for each run of angle bins with no points, wrapping around."""
    bin_indices = (angles / (2 * np.pi) * ANGLE_BIN_COUNT).astype(int) % ANGLE_BIN_COUNT
    filled = np.zeros(ANGLE_BIN_COUNT, dtype=bool)
    filled[bin_indices] = True
    if filled.all() or not filled.any():
        return [], 0
    counts = np.bincount(bin_indices, minlength=ANGLE_BIN_COUNT)
    typical_count = int(np.median(counts[filled]))
    first_filled = int(np.flatnonzero(filled)[0])
    runs = []
    run_start = None
    for step in range(1, ANGLE_BIN_COUNT + 1):
        bin_index = (first_filled + step) % ANGLE_BIN_COUNT
        if not filled[bin_index]:
            if run_start is None:
                run_start = bin_index
        elif run_start is not None:
            runs.append((run_start, (bin_index - run_start) % ANGLE_BIN_COUNT))
            run_start = None
    return runs, typical_count


def slice_skeleton(points, lower_band_height, upper_band_height):
    """Cut the limb into slices between the bands and find the skeleton through them.

    Returns a dictionary: slice_edges (heights), slice_of_point (each point's
    slice index), inside_range (points that fall in some slice), raw_centres
    (one circle-fit centre per slice, NaN where too few points) and skeleton
    (those centres smoothed along the height).
    """
    band_span = upper_band_height - lower_band_height
    margin = band_span * BAND_MARGIN_FRACTION
    slice_edges = np.linspace(lower_band_height - margin, upper_band_height + margin,
                              SLICES_BETWEEN_BANDS + 1)
    slice_count = len(slice_edges) - 1
    slice_of_point = np.digitize(points[:, 2], slice_edges) - 1
    inside_range = (slice_of_point >= 0) & (slice_of_point < slice_count)

    raw_centres = np.full((slice_count, 2), np.nan)
    for slice_index in range(slice_count):
        in_slice = inside_range & (slice_of_point == slice_index)
        if in_slice.sum() >= MINIMUM_POINTS_PER_SLICE:
            raw_centres[slice_index] = fit_circle_centre(points[in_slice, :2])
    skeleton = moving_median(raw_centres, SKELETON_SMOOTHING_SLICES)
    return {"slice_edges": slice_edges, "slice_of_point": slice_of_point,
            "inside_range": inside_range, "raw_centres": raw_centres, "skeleton": skeleton}


def regularize_limb_radii(points, colours, lower_band_height, upper_band_height, seed=0):
    """Move outer and inner defects back toward each slice's smooth curve, and fill empty arcs.

    `points` are levelled (height is +Z); `colours` are uint8 RGB. Returns new
    (points, colours) arrays and a report dictionary with the counts.
    """
    random_generator = np.random.default_rng(seed)
    points = np.asarray(points, dtype=np.float64).copy()
    colours = np.asarray(colours).copy()

    slices = slice_skeleton(points, lower_band_height, upper_band_height)
    slice_edges = slices["slice_edges"]
    slice_of_point = slices["slice_of_point"]
    inside_range = slices["inside_range"]
    skeleton = slices["skeleton"]
    slice_count = len(slice_edges) - 1

    original_points = points.copy()
    outer_count = 0
    inner_count = 0
    added_points = []
    added_colours = []
    arcs_filled = 0
    slices_used = 0
    for slice_index in range(slice_count):
        centre = skeleton[slice_index]
        members = np.flatnonzero(inside_range & (slice_of_point == slice_index))
        if len(members) < MINIMUM_POINTS_PER_SLICE or np.isnan(centre).any():
            continue
        slices_used += 1

        # Fit the curve to this slice and its neighbours, measured from this slice's centre.
        near_slices = inside_range & (np.abs(slice_of_point - slice_index) <= NEIGHBOUR_SLICES)
        fit_offsets = original_points[near_slices, :2] - centre
        fit_angles = np.mod(np.arctan2(fit_offsets[:, 1], fit_offsets[:, 0]), 2 * np.pi)
        fit_radii = np.linalg.norm(fit_offsets, axis=1)
        coefficients = fit_smooth_curve(fit_angles, fit_radii)

        offsets = original_points[members, :2] - centre
        angles = np.mod(np.arctan2(offsets[:, 1], offsets[:, 0]), 2 * np.pi)
        radii = np.linalg.norm(offsets, axis=1)
        expected = curve_radius(coefficients, angles)
        for member_position, point_index in enumerate(members):
            tolerance = RADIUS_TOLERANCE_FRACTION * expected[member_position]
            radius = radii[member_position]
            if radius > expected[member_position] + tolerance:
                new_radius = expected[member_position] + tolerance
                outer_count += 1
            elif radius < expected[member_position] - tolerance:
                new_radius = expected[member_position] - tolerance
                inner_count += 1
            else:
                continue
            angle = angles[member_position]
            points[point_index, 0] = centre[0] + new_radius * np.cos(angle)
            points[point_index, 1] = centre[1] + new_radius * np.sin(angle)

        # Fill each empty arc with points on the curve, at the density of the rest.
        runs, typical_count = empty_arcs(angles)
        slice_colour = np.median(colours[members], axis=0).astype(colours.dtype)
        for gap_start, gap_length in runs:
            if gap_length > LARGEST_GAP_TO_FILL_BINS:
                continue
            arcs_filled += 1
            for step in range(gap_length):
                bin_index = (gap_start + step) % ANGLE_BIN_COUNT
                for _ in range(max(typical_count, 1)):
                    angle = (bin_index + random_generator.random()) * (2 * np.pi / ANGLE_BIN_COUNT)
                    radius = float(curve_radius(coefficients, angle)[0])
                    height = random_generator.uniform(slice_edges[slice_index], slice_edges[slice_index + 1])
                    added_points.append([centre[0] + radius * np.cos(angle),
                                         centre[1] + radius * np.sin(angle),
                                         height])
                    added_colours.append(slice_colour)

    if added_points:
        points = np.vstack([points, np.array(added_points)])
        colours = np.vstack([colours, np.array(added_colours, dtype=colours.dtype)])
    report = {"outer_moved_in": outer_count, "inner_moved_out": inner_count,
              "points_added": len(added_points), "arcs_filled": arcs_filled,
              "slices_used": slices_used}
    return points.astype(np.float32), colours, report
