"""Make the reference cube's points describe a cube: flatten the fuzz, fill the gaps.

The cube sets the scale for every number the pipeline reports, and Stage 6
takes that scale from the cube MESH's volume. So whatever the mesher does to
the cube lands in every measurement. Two things it does badly:

  the fuzz   the points scatter about 2 mm either side of each face, and a
             Poisson surface rides the outside of that scatter
  the gaps   a face seen from too few angles reconstructs with holes, which is
             what makes Poisson tunnel (chi != 2). Stage 4 then falls back to
             the alpha ladder, and the loosest rungs float millimetres clear of
             the points: on 4_circumference_calculation_2c (2026-10-09) the 30x wrap sat 2.9 mm
             proud on every side, 9.1% of volume.

The cube is the one object in the scene whose shape is known exactly, so both
are fixable without inventing anything. An ideal cube is fitted to the points;
every point further than a tolerance from its nearest face is moved onto that
face; then each face is gridded and a point is dropped in the middle of every
empty cell. The bottom face, which always faces the floor, is filled almost
entirely, which is what lets Poisson close without the fallback.

What this does NOT do is decide how big the cube is. The fit is driven by the
points and sits in the middle of their scatter -- on 4_circumference_calculation_2c, 42% of the
points end up outside it and 58% inside, mean offset +0.10 mm. Where the
points say the cube reconstructed small, mending makes the mesh say so too
rather than hiding it under a loose wrap.
"""
import numpy as np

from pipeline.core.cube_fit import fit_cube

DEFAULT_TOLERANCE_MM = 1.0
DEFAULT_CELL_MM = 4.0
REFERENCE_SIDE_CM = 10.0
FACE_NAMES = {(0, 1): "x+", (0, -1): "x-", (1, 1): "y+", (1, -1): "y-",
              (2, 1): "top", (2, -1): "bottom"}


def to_cube_frame(points, fit):
    """Points re-expressed with the cube's own axes and its centre at the origin."""
    yaw = np.radians(fit["yaw_degrees"])
    cosine, sine = np.cos(-yaw), np.sin(-yaw)
    shifted_x = points[:, 0] - fit["centre"][0]
    shifted_y = points[:, 1] - fit["centre"][1]
    return np.column_stack([shifted_x * cosine - shifted_y * sine,
                            shifted_x * sine + shifted_y * cosine,
                            points[:, 2] - (fit["bottom"] + fit["side"] / 2.0)])


def to_scene_frame(local_points, fit):
    """The inverse of to_cube_frame."""
    yaw = np.radians(fit["yaw_degrees"])
    cosine, sine = np.cos(yaw), np.sin(yaw)
    scene_x = local_points[:, 0] * cosine - local_points[:, 1] * sine + fit["centre"][0]
    scene_y = local_points[:, 0] * sine + local_points[:, 1] * cosine + fit["centre"][1]
    scene_z = local_points[:, 2] + fit["bottom"] + fit["side"] / 2.0
    return np.column_stack([scene_x, scene_y, scene_z])


def nearest_face(local_points):
    """For each point, which axis its nearest face lies on and which side of the cube."""
    magnitudes = np.abs(local_points)
    axis = np.argmax(magnitudes, axis=1)
    side = np.sign(local_points[np.arange(len(local_points)), axis])
    return axis, side


def snap_onto_faces(local_points, half_side, tolerance):
    """Move every point further than the tolerance from its nearest face onto that face."""
    axis, _ = nearest_face(local_points)
    rows = np.arange(len(local_points))
    offsets = np.abs(local_points[rows, axis]) - half_side
    moving = np.flatnonzero(np.abs(offsets) > tolerance)

    snapped = local_points.copy()
    snapped[moving, axis[moving]] = np.sign(local_points[moving, axis[moving]]) * half_side
    report = {"pulled_in": int(np.sum(offsets[moving] > 0)),
              "pushed_out": int(np.sum(offsets[moving] < 0)),
              "untouched": int(len(local_points) - len(moving))}
    return snapped, report


def fill_empty_cells(local_points, half_side, cell):
    """Add one point at the centre of every empty cell on every face of the cube."""
    axis, side = nearest_face(local_points)
    steps = max(2, int(np.ceil(2 * half_side / cell)))
    edges = np.linspace(-half_side, half_side, steps + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0

    added = []
    coverage = {}
    for face_axis in (0, 1, 2):
        for face_side in (1, -1):
            on_face = (axis == face_axis) & (side == face_side)
            others = [index for index in (0, 1, 2) if index != face_axis]
            occupied = np.zeros((steps, steps), dtype=bool)
            if on_face.any():
                first = np.clip(np.digitize(local_points[on_face, others[0]], edges) - 1,
                                0, steps - 1)
                second = np.clip(np.digitize(local_points[on_face, others[1]], edges) - 1,
                                 0, steps - 1)
                occupied[first, second] = True
            empty_first, empty_second = np.nonzero(~occupied)
            for first, second in zip(empty_first, empty_second):
                point = np.zeros(3)
                point[face_axis] = face_side * half_side
                point[others[0]] = centres[first]
                point[others[1]] = centres[second]
                added.append(point)
            coverage[FACE_NAMES[(face_axis, face_side)]] = {
                "points": int(on_face.sum()),
                "covered": int(occupied.sum()),
                "cells": steps * steps}
    filled = np.array(added) if added else np.zeros((0, 3))
    return filled, coverage


def mend_reference_points(points, colours, tolerance_mm=DEFAULT_TOLERANCE_MM,
                          cell_mm=DEFAULT_CELL_MM):
    """Flatten and fill the reference cube's points.

    Returns (points, colours, report), or the inputs unchanged with a report of
    None when the cube cannot be fitted. Added points take the mean colour of
    the cloud, so a colour-carrying PLY stays valid.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 0:
        return points, colours, None
    fit = fit_cube(points)
    if fit is None:
        return points, colours, None

    scale_cm_per_unit = REFERENCE_SIDE_CM / fit["side"]
    tolerance = (tolerance_mm / 10.0) / scale_cm_per_unit
    cell = (cell_mm / 10.0) / scale_cm_per_unit
    half_side = fit["side"] / 2.0

    local = to_cube_frame(points, fit)
    snapped, snap_report = snap_onto_faces(local, half_side, tolerance)
    added, coverage = fill_empty_cells(snapped, half_side, cell)

    mended_local = np.vstack([snapped, added]) if len(added) else snapped
    mended_points = to_scene_frame(mended_local, fit)

    mended_colours = colours
    if colours is not None and len(colours) == len(points):
        colours = np.asarray(colours)
        if len(added):
            fill_colour = np.tile(colours.mean(axis=0), (len(added), 1))
            mended_colours = np.vstack([colours, fill_colour])

    report = {"fitted_side_cm": REFERENCE_SIDE_CM,
              "scale_cm_per_unit": scale_cm_per_unit,
              "residual_mm": fit["residual"] * scale_cm_per_unit * 10,
              "added": int(len(added)),
              "coverage": coverage,
              **snap_report}
    return mended_points, mended_colours, report


def describe(report):
    """One line for the run log, or None when nothing was mended."""
    if report is None:
        return None
    worst_name, worst_face = min(report["coverage"].items(),
                                 key=lambda item: item[1]["covered"] / item[1]["cells"])
    worst_percent = 100 * worst_face["covered"] / worst_face["cells"]
    return (f"Box mending: {report['pulled_in']} pulled in, {report['pushed_out']} pushed out, "
            f"{report['untouched']} untouched, {report['added']} added to empty cells "
            f"(thinnest face {worst_name} at {worst_percent:.0f}% covered, "
            f"points were {report['residual_mm']:.2f} mm off a true cube)")
