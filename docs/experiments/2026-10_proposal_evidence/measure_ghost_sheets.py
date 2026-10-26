"""Measure where the reconstructed limb surface splits into two sheets.

In a thin horizontal slice the limb's cross-section should be a single closed
ring. It is not: over part of its circumference the points fall into two arcs
several millimetres apart. The old pipeline applies no moving-least-squares
projection and has no ghost filter, so whatever splitting the geometry model
produces survives into its reconstruction.

The question is asked per angular wedge rather than over the whole surface.
That matters: the two sheets coincide over most of the circumference and
separate only in places, so any statistic that takes a median over the whole
surface averages the defect away. Three such statistics were tried first and
all three reported the limb as no worse than the rigid reference cube. See
FINDINGS.md.

The control is a rigid can. It is cylindrical, so the radial wedge measure
applies to it as it does not to the square reference cube, whose corners would
register as false splits. It is also rigid and cannot move between
photographs.

    python docs/experiments/2026-10_proposal_evidence/measure_ghost_sheets.py
"""
import pathlib
import sys

import numpy as np

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core.cube3d import reference_points_from_dirs
from pipeline.stages.clean import _load_and_thin, _split_into_objects

# Width of one angular wedge, in degrees. Narrow enough that a limb's true
# radius barely changes across it, wide enough to hold points from several
# photographs.
WEDGE_DEGREES = 5.0

# Below this a wedge is too sparse for its radii to mean anything.
MINIMUM_POINTS_PER_WEDGE = 8

# Radial gap, in millimetres, above which two groups of points within one wedge
# are separate sheets rather than the thickness of a single one. A single sheet
# measures about 2 mm thick over a 3 mm neighbourhood, so 3 mm clears it.
SHEET_GAP_MM = 3.0

# Half-thickness of the slice, in millimetres.
SLAB_HALF_MM = 1.0

# Heights, as a fraction of the object's length, that each object is sliced at.
SLICE_FRACTIONS = (0.35, 0.45, 0.55, 0.65)

# The rigid cylindrical control, then the limbs.
CONTROL = ("rigid can", "work/fanta_orange", "00_prep",
           "01_inference/predictions.npz", "02_pointcloud/points.ply")
LIMBS = ["output_test2_keng", "output_test2_sunshine", "output_test2_champ"]


def sheets_in_wedge(radii_mm):
    """Split one wedge's radii into sheets wherever a gap exceeds the threshold."""
    ordered = np.sort(radii_mm)
    breaks = np.flatnonzero(np.diff(ordered) > SHEET_GAP_MM)
    groups = np.split(ordered, breaks + 1)
    kept = []
    for group in groups:
        if len(group) >= 2:
            kept.append(group)
    return kept


def analyse_object(points, units_per_mm):
    """Wedges measured, wedges split, and the separations found, for one object."""
    extent = points.max(axis=0) - points.min(axis=0)
    long_axis = int(np.argmax(extent))
    along = points[:, long_axis]

    measured = 0
    split = 0
    separations = []
    for fraction in SLICE_FRACTIONS:
        height = along.min() + fraction * (along.max() - along.min())
        in_slab = np.abs(along - height) < SLAB_HALF_MM * units_per_mm
        if in_slab.sum() < 200:
            continue
        flat = np.delete(points[in_slab], long_axis, axis=1) / units_per_mm
        offsets = flat - np.median(flat, axis=0)
        radii = np.linalg.norm(offsets, axis=1)
        angles = np.degrees(np.arctan2(offsets[:, 1], offsets[:, 0])) % 360

        for start in np.arange(0, 360, WEDGE_DEGREES):
            inside = (angles >= start) & (angles < start + WEDGE_DEGREES)
            if inside.sum() < MINIMUM_POINTS_PER_WEDGE:
                continue
            measured += 1
            sheets = sheets_in_wedge(radii[inside])
            if len(sheets) >= 2:
                split += 1
                centres = []
                for sheet in sheets:
                    centres.append(float(np.median(sheet)))
                separations.append(max(centres) - min(centres))
    return measured, split, separations


def load_object(prep_directory, predictions_path, dense_path):
    """The subject cluster and the millimetre scale, from one finished run."""
    projected = reference_points_from_dirs(str(prep_directory),
                                           str(predictions_path), verbose=False)
    dense_cloud = _load_and_thin(str(dense_path))
    cube_cluster, subject_cluster = _split_into_objects(dense_cloud, 2, projected)
    if subject_cluster is None:
        return None, None

    # The reference cube's known 10 cm side is the only real length in the
    # scene. The median of its three bounding-box extents is used because a
    # reconstructed cube is not exactly a cube.
    cube_points = np.asarray(cube_cluster.points)
    cube_extent = cube_points.max(axis=0) - cube_points.min(axis=0)
    units_per_mm = float(np.median(cube_extent)) / 100.0
    return np.asarray(subject_cluster.points), units_per_mm


def report(label, points, units_per_mm):
    """Print one object's row of the comparison."""
    measured, split, separations = analyse_object(points, units_per_mm)
    if measured == 0:
        print(f"{label:<34}{'no slice had enough points':>39}")
        return
    percent = 100.0 * split / measured
    if separations:
        gap = float(np.median(separations))
    else:
        gap = float("nan")
    print(f"{label:<34}{measured:>8}{split:>8}{percent:>9.1f}%{gap:>11.1f}mm")


def main():
    """Measure the control, then every limb capture."""
    slice_labels = []
    for fraction in SLICE_FRACTIONS:
        slice_labels.append(f"{fraction:.0%}")
    print(f"{WEDGE_DEGREES:.0f} degree wedges, sheets separated by more than "
          f"{SHEET_GAP_MM:.0f} mm, slices at "
          f"{', '.join(slice_labels)} of height\n")
    header = (f"{'object':<34}{'wedges':>8}{'split':>8}{'% split':>10}"
              f"{'median gap':>13}")
    print(header)
    print("-" * len(header))

    name, root, prep, predictions, dense = CONTROL
    points, units_per_mm = load_object(PROJECT_ROOT / root / prep,
                                       PROJECT_ROOT / root / predictions,
                                       PROJECT_ROOT / root / dense)
    if points is None:
        print(f"{name:<34}  could not be separated into two clusters")
    else:
        report(f"{name} ({pathlib.Path(root).name})", points, units_per_mm)

    for run_directory in LIMBS:
        debug = PROJECT_ROOT / run_directory / "for_debug"
        points, units_per_mm = load_object(
            debug / "00_prep", debug / "01_inference" / "predictions.npz",
            debug / "02_pointcloud" / "points.ply")
        if points is None:
            print(f"{run_directory:<34}  could not be separated")
            continue
        report("limb (" + run_directory.replace("output_", "") + ")",
               points, units_per_mm)


if __name__ == "__main__":
    main()
