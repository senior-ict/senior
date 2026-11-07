# Ground truth from a 3D scan

The reference volume for era 6 (`inputs/6_3d_scanner_*`) comes from an Einstar
scan of the limb with the marker bands still tied on. Because the bands are in
the scan, the same two cutting planes the pipeline uses can be placed on the
same two cords, and the reference is measured the way a reconstruction is: a
capped plane slice at each band's inner edge, then the exact volume of the
resulting watertight mesh.

That matters more than it sounds. A reference measured one way and a
reconstruction measured another differ by the methods as well as by the limb,
and the difference is then charged to the pipeline. Here nothing about the
measurement differs between the two sides.

## The scripts

    scan_gt_pipeline_method.py   the reference volume, span and circumferences
    gt_vs_pipeline.py            a run against the reference, error attributed
    scan_band_circumference.py   band detection and the limb at each inner edge
    segment_cut.py               the capped two plane cut, self contained

Run them with the repository root as the working directory:

    python tools/scan_ground_truth/scan_gt_pipeline_method.py \
        --scan inputs/6_3d_scanner_2k/keng_r_2.ply --label gt2k

    python tools/scan_ground_truth/gt_vs_pipeline.py \
        --scan inputs/6_3d_scanner_2k/keng_r_2.ply \
        --run work/gt2k --cm-per-unit 90.6301 --label gt2k

`segment_cut.py` keeps its own copy of the two plane cut rather than importing
`pipeline/core/meshcut.py`. Only the newest branch has that module, and a
reference that reproduces on one branch only is not much of a reference. The
two agree: both routes return 1566.8 cm3 on `6_3d_scanner_2k`.

Add `--repair` to fill holes and drop stray pieces before cutting, which is
what Stage 5 does to a reconstruction. A scan that the scanner left open needs
it. It is slow on a mesh of several hundred thousand faces.

## The scanner was checked before it was trusted

It reads a 100 mm reference cube at 99.50 mm, which is -0.50%, and reads a flat
floor flat to 0.203 mm. Two scans of one leg taken minutes apart agree to
1.5 mm in circumference.

## The scan meshes are not in this repository

They total 519 MB and one file is over GitHub's 100 MB limit, so the `.ply` and
`.asc` files are kept outside version control. The photographs of each capture
and the measured reference values are committed;
`inputs/groundtruth6_3d_scanner.csv` holds the values.

## This reference disagrees with era 5 in sign

A tape compresses soft tissue and a scan does not, so a tape reads the same
limb small, by 1.3% to 7.2%, and by more at the fleshy upper band than at the
ankle. An error measured against a tape and the same error measured against a
scan point in opposite directions. The two cannot be mixed.

## Two captures carry no reference volume yet

`6_3d_scanner_1k` defeats the band detection, which reads 45.44 cm at its ankle
band, wider than its knee band, so neither its span nor its volume can be
trusted. `6_3d_scanner_3c` was left open by the scanner, so its cut segment is
not watertight and the exact volume method does not apply until its holes are
filled.
