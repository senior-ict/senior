# Test captures, 2026-09-18

Six limb captures and two cans, measured against a tape rather than water.
Inputs are `inputs/test1` … `inputs/test6`, `inputs/fanta_orange`,
`inputs/fanta_red`. Run outputs are not committed; each regenerates with
`python run.py -i inputs/<name> --output_dir output_<name>` in a few minutes.

## What was found

**The model measures circumference correctly.** On a slim 325 mL can
(`fanta_orange`, taped girth 18.5 cm), the pipeline read **+0.9%** with a/b of
1.01–1.03 and 100% ring coverage. Height read +6.8% — loose end caps from the
alpha fallback — so a whole-object volume runs ~+5–10% high even when the girth
is exact.

**The limb over-read is therefore limb-specific**, and it decomposes:

| term | `test6`, hairless shin | how it was measured |
|---|---|---|
| cube-derived scale | +4.2% linear → ×1.133 | ruler 27.5 cm between bands vs pipeline 28.7 |
| residual girth | +5.5% → ×1.114 | profile vs tape, scale removed |
| alpha wrap | ×1.10 | mesh section area vs points, per slice (`ring_gallery.png`) |
| product | ×1.387 | measured +38.7% |

On `test5` (hairy male shin) the shin rows read **+19%** against +4% at the
ankle and calf; `test6`, nearly hairless, has no shin spike. The spike is hair.

**Whether the cube is physically 9.6 cm or reconstructs small is unresolved**
— a caliper on its edge decides it, and it is worth 13% of every volume.

## What was ruled out

- **Motion.** Girth error anti-correlates with height (−0.32) and with surface
  scatter (−0.19); four capture styles on `test1`–`test4` gave the same error.
- **Outlier trimming at the cross-section.** The shell is ~15 mm thick with an
  inward tail; six trim rules moved girth by ≤0.4%. The ring is in the wrong
  place, not contaminated.
- **Ring coverage.** `test4` had 100% coverage and still read +10.9%.
- **Reconstruction method.** Circumference is measured from the Stage 3 cloud
  and is byte-identical under Poisson and alpha_shape. alpha_shape made the
  *volume* worse (+17% on `test1`).

## The wrap

`ring_gallery.png` slices `test6` every 2 cm and overlays the watertight mesh's
cross-section on the cleaned points. From 14 cm up, one side of the limb shows
a second arc ~1 cm inside the outer one — the ghost double-sheet — and the
30× nn alpha wrap bridges straight across the outer strays. Mesh section area
exceeds the points' ellipse by 13–17% on those slices, **+12.0% summed**.

Poisson tunnelled (χ from −2 to −22) on 5 of 8 runs, forcing that fallback.
The alpha ladder is already optimal: a finer search between its rungs on
`test5` found nothing tighter than the 25× it chose.

## Two environment failure modes

- **Reflective floor.** RANSAC removed 20–33% of the floor instead of ~70%;
  `fanta_red` came out as a 15 L "can" with a cube fill of 0.359. Shoot on the
  matte tile.
- **Degraded WSL GPU.** Inference went from 14 s to 320–520 s with the GPU at
  100% / 7.9 GB and nothing else on it. RAM and swap were a red herring.
  `wsl --shutdown` resets it.

## Tape repeatability

Measured on `test5`, two passes: 0.8 cm mean / 2 cm worst on girth, 2 cm on
band separation (7% of volume). Water displacement and tape agreed to 4%.

## Files

| file | what |
|---|---|
| `test5_diagnostic.png` | band cross-sections vs taped circles, shell histogram, girth profile |
| `test5_profile_vs_tape.png` | 2 cm tape profile vs pipeline, by height, with error bars |
| `ring_gallery.png` | every slice of `test6` with the mesh section overlaid |
| `test6_tape_profile.csv` | the taped profile, for `tools/limb_volume_from_tape.py` |
| `visualise_test5.py`, `ring_gallery.py` | regenerate the figures from a run directory |
