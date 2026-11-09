"""Move each cutting plane from the middle of its painted band to the band's inner edge.

The bands are stripes about 1.3 cm wide, not lines, so "the distance between the
bands" is ambiguous by one stripe width, and that ambiguity is the pipeline's
largest single error. Measured on 2026-10-09, sliding both planes from the
stripes' inner edges to their outer edges swings the limb volume by 15-35%:

    5_circumference_calculation_1k   26.30 cm inner -> 30.79 cm outer, 1404 cm3 -> 1629 cm3
    test6        26.41 cm inner -> 32.42 cm outer, 1363 cm3 -> 1696 cm3

The tape is read between the bands' INNER edges, so that is where the planes
belong. Cutting at the stripe centres instead, which is where a plane fitted
to the whole stripe lands, made three tape captures read +6.9%, +6.9% and
+4.8%; cutting at the inner edges made them -0.2%, -1.9% and -1.6%.

Each plane keeps the orientation Stage 3 fitted to its band -- only its
position moves.

HOW THE EDGE IS FOUND, and why it changed on 2026-11-09
-------------------------------------------------------
The original version measured every band point's position along the line
joining the two band CENTRES, then took the 2nd and 98th percentile of those.
Both halves of that were wrong, and against Einstar scans of the same four
legs they cost 5.7 mm per band on average and 13.2 mm at worst.

1. THE DIRECTION. A band tied round a tapering calf sits at an angle, 3 to 15
   degrees away from the line joining the two bands. Measured along that line
   rather than along the band's own normal, the tilt is counted as width: on
   capture 4s's upper band a 1.30 cm cord read as 3.04 cm, and the edge was
   placed 1.04 cm too far in. The band's own normal was always available in
   `markers` and was simply not used. Measuring along it drops the mean error
   to 1.7 mm.

2. THE STATISTIC. One percentile over the whole band is decided by a handful of
   points, so a patch of colour bleed anywhere on the ring moves the cut. The
   limb is instead cut into wedges; the innermost band point in each wedge is
   one estimate of the edge, and the cut goes at the mode of those estimates.
   On the four scanned captures the wedge estimates agree with each other to
   3 to 4 mm, so the edge is a real ring and a single bad wedge is outvoted.

Measured against the scans, per band, in millimetres from where the scan cuts:

    method                                 mean |error|   worst
    along the inter-band axis (before)          5.7        13.2
    whole-band extreme, along the normal        1.7         3.0
    wedge edges, their mode (now)               2.0         2.7

The two new methods score the same within the noise of six bands. The wedge
mode is used because its worst case is better and because it cannot be moved
by one stray point, which is the failure the simple version is exposed to and
these six bands happen not to contain.

`BAND_EDGE_METHOD = "axis"` restores the original behaviour exactly.

STILL OPEN: both new methods sit about 2 mm less far in than the scan on five
of the six bands. That may be ours or it may be the reference: the scan finds
its own edge with the same whole-band 98th percentile, on a cord whose colour
also bleeds onto skin, which would push the scan's plane too far in. Untested.
"""
import numpy as np

BAND_GREEN_EXCESS = 0.06      # how much greener than grey a band point is
EDGE_PERCENTILE = 2.0         # ignore the outermost 2% as colour bleed
SEARCH_WINDOW_CM = 4.0        # how far either side of a plane to look for its stripe
MINIMUM_BAND_POINTS = 40

# Wedge settings. Ten degrees gives 36 wedges, of which 34 to 36 are usable on
# the scanned captures, and their edge estimates agree to 3 to 4 mm.
WEDGE_DEGREES = 10.0
MINIMUM_POINTS_PER_WEDGE = 3
MINIMUM_USABLE_WEDGES = 12
DENSITY_GRID_STEPS = 400


def band_coloured(colours):
    """Which points are band-green: green above the average of red and blue."""
    colours = np.asarray(colours, dtype=np.float64)
    if colours.max() > 1.5:          # 0-255 rather than 0-1
        colours = colours / 255.0
    red, green, blue = colours[:, 0], colours[:, 1], colours[:, 2]
    return (green - (red + blue) / 2.0) > BAND_GREEN_EXCESS


def stripe_span(points, is_band, origin, axis, centre_along, window):
    """Where one stripe starts and ends along the axis, or None if too few points."""
    along = (points - origin) @ axis
    near = is_band & (np.abs(along - centre_along) < window)
    if near.sum() < MINIMUM_BAND_POINTS:
        return None
    positions = along[near]
    low = float(np.percentile(positions, EDGE_PERCENTILE))
    high = float(np.percentile(positions, 100 - EDGE_PERCENTILE))
    return low, high, int(near.sum())


def thickest_value(values):
    """Where a set of values is densest, falling back to the median if too few.

    A mode rather than a mean, so a few wedges whose edge was pushed out by
    colour bleed cannot drag the answer. scipy is optional here on purpose:
    this module is imported by Stage 3 and should not fail a run if the
    density estimate cannot be built.
    """
    values = np.asarray(values, dtype=np.float64)
    if len(values) < 5:
        return float(np.median(values))
    try:
        from scipy.stats import gaussian_kde

        grid = np.linspace(values.min(), values.max(), DENSITY_GRID_STEPS)
        return float(grid[int(np.argmax(gaussian_kde(values)(grid)))])
    except Exception:
        return float(np.median(values))


def wedge_inner_offset(band_points, centre, inward_normal):
    """How far the band's inner edge sits from its centre, along the band's normal.

    The limb is cut into wedges around `inward_normal`. The band point furthest
    inward in each wedge is that wedge's estimate of the edge, and the answer
    is the mode of those estimates. Returns (offset, wedges_used, spread) or
    None when too few wedges hold enough points to vote.
    """
    offsets = np.asarray(band_points, dtype=np.float64) - centre
    inward = offsets @ inward_normal
    in_plane = offsets - np.outer(inward, inward_normal)

    lengths = np.linalg.norm(in_plane, axis=1)
    if not len(lengths) or lengths.max() <= 0:
        return None
    first_across = in_plane[int(np.argmax(lengths))]
    first_across = first_across / np.linalg.norm(first_across)
    second_across = np.cross(inward_normal, first_across)
    angle = np.degrees(np.arctan2(in_plane @ second_across,
                                  in_plane @ first_across)) % 360.0

    wedge_of = (angle // WEDGE_DEGREES).astype(int)
    edges = []
    for wedge in np.unique(wedge_of):
        inside = wedge_of == wedge
        if inside.sum() < MINIMUM_POINTS_PER_WEDGE:
            continue
        edges.append(float(inward[inside].max()))
    if len(edges) < MINIMUM_USABLE_WEDGES:
        return None

    edges = np.asarray(edges)
    spread = float(np.percentile(edges, 90) - np.percentile(edges, 10))
    return thickest_value(edges), len(edges), spread


def _inward_normal(marker, own_centre, other_centre):
    """Returns the band's own normal, pointed toward the other band."""
    normal = np.asarray(marker["normal"], dtype=np.float64)
    length = np.linalg.norm(normal)
    if length <= 0:
        return None
    normal = normal / length
    if float(normal @ (other_centre - own_centre)) < 0.0:
        normal = -normal
    return normal


def _move_along_own_normals(markers, points, colours, window):
    """Slides each plane to its band's inner edge, along that band's own normal.

    Returns (markers, report) or (None, None) when either band cannot be
    measured this way, so the caller can fall back.
    """
    lower_centre = np.asarray(markers[0]["centroid"], dtype=np.float64)
    upper_centre = np.asarray(markers[-1]["centroid"], dtype=np.float64)
    is_band = band_coloured(colours)

    moved, measurements = [], []
    for marker, own_centre, other_centre in (
            (markers[0], lower_centre, upper_centre),
            (markers[-1], upper_centre, lower_centre)):
        normal = _inward_normal(marker, own_centre, other_centre)
        if normal is None:
            return None, None

        # The stripe's own points: band green, and within the search window of
        # this band's centre measured along this band's normal.
        along_own = (points - own_centre) @ normal
        near = is_band & (np.abs(along_own) < window)
        if near.sum() < MINIMUM_BAND_POINTS:
            return None, None

        found = wedge_inner_offset(points[near], own_centre, normal)
        if found is None:
            return None, None
        offset, wedges_used, spread = found

        shifted = dict(marker)
        shifted["centroid"] = (own_centre + normal * offset).tolist()
        shifted["moved_to"] = "inner_edge"
        moved.append(shifted)
        measurements.append({"offset": offset, "wedges": wedges_used,
                             "spread": spread, "points": int(near.sum()),
                             "width": float(along_own[near].max()
                                            - along_own[near].min())})

    # The two planes must still face each other across a segment.
    new_lower = np.asarray(moved[0]["centroid"], dtype=np.float64)
    new_upper = np.asarray(moved[-1]["centroid"], dtype=np.float64)
    axis = upper_centre - lower_centre
    centre_span = float(np.linalg.norm(axis))
    axis = axis / centre_span
    inner_span = float((new_upper - new_lower) @ axis)
    if inner_span <= 0:
        return None, None

    report = {"method": "wedge",
              "centre_span": centre_span,
              "inner_span": inner_span,
              "lower_stripe_width": measurements[0]["width"],
              "upper_stripe_width": measurements[1]["width"],
              "lower_points": measurements[0]["points"],
              "upper_points": measurements[1]["points"],
              "lower_wedges": measurements[0]["wedges"],
              "upper_wedges": measurements[1]["wedges"],
              "lower_wedge_spread": measurements[0]["spread"],
              "upper_wedge_spread": measurements[1]["spread"]}
    return moved, report


def _move_along_inter_band_axis(markers, points, colours, window):
    """The original method: percentiles along the line joining the two centres.

    Kept so `BAND_EDGE_METHOD = "axis"` reproduces every number measured before
    2026-11-09 exactly.
    """
    lower_centre = np.asarray(markers[0]["centroid"], dtype=np.float64)
    upper_centre = np.asarray(markers[-1]["centroid"], dtype=np.float64)
    axis = upper_centre - lower_centre
    centre_span = float(np.linalg.norm(axis))
    if centre_span <= 0:
        return None, None
    axis = axis / centre_span

    is_band = band_coloured(colours)
    lower_stripe = stripe_span(points, is_band, lower_centre, axis, 0.0, window)
    upper_stripe = stripe_span(points, is_band, lower_centre, axis, centre_span,
                               window)
    if lower_stripe is None or upper_stripe is None:
        return None, None

    lower_inner = lower_stripe[1]
    upper_inner = upper_stripe[0]
    if upper_inner <= lower_inner:
        return None, None

    moved = []
    for marker, offset in zip((markers[0], markers[-1]),
                              (lower_inner, upper_inner)):
        shifted = dict(marker)
        shifted["centroid"] = (lower_centre + axis * offset).tolist()
        shifted["moved_to"] = "inner_edge"
        moved.append(shifted)

    report = {"method": "axis",
              "centre_span": centre_span,
              "inner_span": upper_inner - lower_inner,
              "lower_stripe_width": lower_stripe[1] - lower_stripe[0],
              "upper_stripe_width": upper_stripe[1] - upper_stripe[0],
              "lower_points": lower_stripe[2],
              "upper_points": upper_stripe[2]}
    return moved, report


def move_planes_to_inner_edges(markers, points, colours, scale_cm_per_unit=None):
    """Slide the lower plane up and the upper plane down, each to its stripe's inner edge.

    `markers` is Stage 3's list of {centroid, normal, ...} in levelled space,
    lowest first. Returns (markers, report); the markers are returned unchanged
    when there are not exactly two of them or a stripe cannot be found.

    The default method measures each band along its own normal and finds the
    edge by wedge vote. It falls back to the original inter-band-axis method
    when a band cannot be measured that way, and says so in the report, rather
    than leaving the planes at the stripe centres.
    """
    if (len(markers) != 2 or len(points) == 0 or colours is None
            or len(colours) != len(points)):
        return markers, None

    try:
        from pipeline.config import BAND_EDGE_METHOD
    except Exception:
        BAND_EDGE_METHOD = "wedge"

    points = np.asarray(points, dtype=np.float64)
    lower_centre = np.asarray(markers[0]["centroid"], dtype=np.float64)
    upper_centre = np.asarray(markers[-1]["centroid"], dtype=np.float64)
    centre_span = float(np.linalg.norm(upper_centre - lower_centre))
    if centre_span <= 0:
        return markers, None
    window = (SEARCH_WINDOW_CM / scale_cm_per_unit if scale_cm_per_unit
              else centre_span * 0.15)

    if BAND_EDGE_METHOD == "wedge":
        moved, report = _move_along_own_normals(markers, points, colours, window)
        if moved is not None:
            return moved, report
        moved, report = _move_along_inter_band_axis(markers, points, colours,
                                                    window)
        if moved is not None:
            report["method"] = "axis (fell back, a band could not be measured "
            report["method"] += "along its own normal)"
            return moved, report
        return markers, None

    moved, report = _move_along_inter_band_axis(markers, points, colours, window)
    if moved is None:
        return markers, None
    return moved, report


def describe(report, scale_cm_per_unit=None):
    """One line for the run log, or None when the planes were left alone."""
    if report is None:
        return None
    if scale_cm_per_unit:
        line = (f"Band planes moved to the stripes' inner edges "
                f"[{report['method']}]: span "
                f"{report['centre_span'] * scale_cm_per_unit:.2f} cm centre to centre -> "
                f"{report['inner_span'] * scale_cm_per_unit:.2f} cm inner to inner "
                f"(stripes {report['lower_stripe_width'] * scale_cm_per_unit:.2f} and "
                f"{report['upper_stripe_width'] * scale_cm_per_unit:.2f} cm wide)")
        if "lower_wedges" in report:
            line += (f"; wedges {report['lower_wedges']} and "
                     f"{report['upper_wedges']}, agreeing to "
                     f"{report['lower_wedge_spread'] * scale_cm_per_unit * 10:.0f} "
                     f"and "
                     f"{report['upper_wedge_spread'] * scale_cm_per_unit * 10:.0f} mm")
        return line
    return (f"Band planes moved to the stripes' inner edges "
            f"[{report['method']}]: span "
            f"{report['centre_span']:.4f} -> {report['inner_span']:.4f} scene units")
