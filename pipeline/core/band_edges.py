"""Move each cutting plane from the middle of its painted band to the band's inner edge.

The bands are stripes about 2 cm wide, not lines, so "the distance between the
bands" is ambiguous by one stripe width, and that ambiguity is the pipeline's
largest single error. Measured on 2026-10-09, sliding both planes from the
stripes' inner edges to their outer edges swings the limb volume by 15-35%:

    4_circumference_calculation_1k   26.30 cm inner -> 30.79 cm outer, 1404 cm3 -> 1629 cm3
    test6        26.41 cm inner -> 32.42 cm outer, 1363 cm3 -> 1696 cm3

The tape is read between the bands' INNER edges, so that is where the planes
belong. Cutting at the stripe centres instead, which is where a plane fitted
to the whole stripe lands, made three tape captures read +6.9%, +6.9% and
+4.8%; cutting at the inner edges made them -0.2%, -1.9% and -1.6%.

Each plane keeps the orientation Stage 3 fitted to its band -- only its
position moves, along the line joining the two band centres.
"""
import numpy as np

BAND_GREEN_EXCESS = 0.06      # how much greener than grey a band point is
EDGE_PERCENTILE = 2.0         # ignore the outermost 2% as colour bleed
SEARCH_WINDOW_CM = 4.0        # how far either side of a plane to look for its stripe
MINIMUM_BAND_POINTS = 40


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


def move_planes_to_inner_edges(markers, points, colours, scale_cm_per_unit=None):
    """Slide the lower plane up and the upper plane down, each to its stripe's inner edge.

    `markers` is Stage 3's list of {centroid, normal, ...} in levelled space,
    lowest first. Returns (markers, report); the markers are returned unchanged
    when there are not exactly two of them or a stripe cannot be found.
    """
    if len(markers) != 2 or len(points) == 0 or colours is None or len(colours) != len(points):
        return markers, None

    points = np.asarray(points, dtype=np.float64)
    lower_centre = np.asarray(markers[0]["centroid"], dtype=np.float64)
    upper_centre = np.asarray(markers[-1]["centroid"], dtype=np.float64)
    axis = upper_centre - lower_centre
    centre_span = float(np.linalg.norm(axis))
    if centre_span <= 0:
        return markers, None
    axis = axis / centre_span

    window = SEARCH_WINDOW_CM / scale_cm_per_unit if scale_cm_per_unit else centre_span * 0.15
    is_band = band_coloured(colours)
    lower_stripe = stripe_span(points, is_band, lower_centre, axis, 0.0, window)
    upper_stripe = stripe_span(points, is_band, lower_centre, axis, centre_span, window)
    if lower_stripe is None or upper_stripe is None:
        return markers, None

    # The inner edge of the lower stripe is its top; of the upper stripe, its bottom.
    lower_inner = lower_stripe[1]
    upper_inner = upper_stripe[0]
    if upper_inner <= lower_inner:
        return markers, None

    moved = []
    for marker, offset in zip((markers[0], markers[-1]), (lower_inner, upper_inner)):
        shifted = dict(marker)
        shifted["centroid"] = (lower_centre + axis * offset).tolist()
        shifted["moved_to"] = "inner_edge"
        moved.append(shifted)

    report = {"centre_span": centre_span,
              "inner_span": upper_inner - lower_inner,
              "lower_stripe_width": lower_stripe[1] - lower_stripe[0],
              "upper_stripe_width": upper_stripe[1] - upper_stripe[0],
              "lower_points": lower_stripe[2],
              "upper_points": upper_stripe[2]}
    return moved, report


def describe(report, scale_cm_per_unit=None):
    """One line for the run log, or None when the planes were left alone."""
    if report is None:
        return None
    if scale_cm_per_unit:
        return (f"Band planes moved to the stripes' inner edges: span "
                f"{report['centre_span'] * scale_cm_per_unit:.2f} cm centre to centre -> "
                f"{report['inner_span'] * scale_cm_per_unit:.2f} cm inner to inner "
                f"(stripes {report['lower_stripe_width'] * scale_cm_per_unit:.2f} and "
                f"{report['upper_stripe_width'] * scale_cm_per_unit:.2f} cm wide)")
    return (f"Band planes moved to the stripes' inner edges: span "
            f"{report['centre_span']:.4f} -> {report['inner_span']:.4f} scene units")
