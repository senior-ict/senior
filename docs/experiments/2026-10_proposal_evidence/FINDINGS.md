# Proposal evidence, measured 2026-10-27

Evidence gathered for Chapter 4 of the proposal, on the pipeline the report
evaluates (the old pipeline, `old-pipeline` at commit 537e216).

## The reconstructed limb surface splits into two sheets

In a 2 mm horizontal slice the limb's cross-section is not a single closed
ring. Over part of its circumference the points fall into two separate arcs
several millimetres apart. `limb_cross_sections.png` shows three captures;
the splitting is clearest on `test2_champ` at the left of its section and on
`test2_keng` at the upper left and right.

Measured by dividing each slice into 5 degree wedges and asking whether that
wedge's points fall into one radial group or several, with groups separated by
a gap of more than 3 mm. Four slices per object, at 35, 45, 55 and 65 per cent
of its height.

| object | wedges | split | % split | median gap |
|---|---|---|---|---|
| rigid can (`work/fanta_orange`) | 283 | 2 | **0.7%** | 3.8 mm |
| limb (`test2_sunshine`) | 68 | 10 | **14.7%** | 7.0 mm |
| limb (`test2_champ`) | 88 | 25 | **28.4%** | 6.8 mm |
| limb (`test2_keng`) | 113 | 53 | **46.9%** | 7.6 mm |

**The control.** The can is cylindrical, so the radial wedge measure applies to
it as it does not to the square reference cube, whose corners register as false
splits. It is also rigid and cannot move between photographs. It splits in 2
wedges of 283.

**What this does and does not show.** The splitting is real and is specific to
limbs; a rigid object of the same shape reconstructs as a single clean ring. It
does **not** establish that subject movement is the cause. A limb is a harder
subject than a printed aluminium can regardless of movement: less surface
texture, hair, and more self-occlusion. The measurement separates "limb" from
"rigid cylinder", not "movement" from "model".

## Three measures that did not detect it, and why

Recorded because each looked reasonable and each was wrong, and because a
reader may propose one of them.

| measure | limb | reference cube | why it failed |
|---|---|---|---|
| per-cell sheet separation | 2.40-2.70 mm | 1.75-2.56 mm | a median over four points per frame per cell is noise |
| pooled per-frame bias span | 0.34-1.03 mm | 0.81-1.46 mm | the sheets are not one frame against another |
| local surface thickness | 2.32-2.93 mm | 2.67-3.16 mm | a median over the whole surface averages away a defect present on part of it |

All three report the limb as no worse than the reference cube. The defect is
present on 15 to 47 per cent of the circumference and absent on the rest, so
any statistic that takes a median over the whole surface hides it. Looking at a
slice found in one figure what three statistics missed.

## The old pipeline has no step that merges the sheets

    git show old-pipeline:pipeline/stages/clean.py | grep -c -E "mls|MLS"   ->  0
    grep -c -E "mls|MLS" pipeline/stages/clean.py                           -> 17

The old pipeline also has no `pipeline/ghost.py`. Its only surface cleaning is
`remove_statistical_outlier`.

## Reproducing

    python docs/experiments/2026-10_proposal_evidence/measure_ghost_sheets.py
