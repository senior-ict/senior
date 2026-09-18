# Weekly report — 18 to 19 September 2026

Branch `keng-branch`, commits `fba55eb` through the docs reorganisation.
Timestamps are the commit times. The model-swap experiment lives on a
separate branch, `model-swap`, in its own worktree, so the main pipeline
carries none of it.

## The question the week set out to answer

Every limb measured so far reads 20–40% more volume between its two marker
bands than tape or water says. The week's work was to find where that comes
from. The short answer: not the reference cube, not the camera, not the
image resolution, not the cleaning, and not only VGGT. Two reconstruction
models return the same fat, long leg, while a rigid can beside the cube
measures within 2%. What is left is either scale drifting away from the
floor reference or a bias this family of models has on textureless skin,
and two cheap captures decide between them (a ruler beside the bare leg,
then a patterned stocking on it).

Along the way four real defects in the pipeline were found and fixed, and
one was validated and made the default.

## What changed in the pipeline

| when | commit | change | effect, measured |
|---|---|---|---|
| Thu 18 Sep 23:46 | `050a89d` | Second, wider MLS pass on the limb (`MLS_SECOND_RADIUS_MULT`), off by default | test6 1939.4 (+38.7%, alpha fallback) to 1703.9 (+21.8%, Poisson closes); can girth unchanged |
| Fri 19 Sep 01:46 | `e511244` | Ghost voxel spacing bug fixed: the estimator measured a 5,000-point sample's own spacing, so cleaning got coarser as clouds got denser. Factor rescaled so validated runs keep their voxel | Full-resolution originals of test6 went from +32.2% to the same cleaning as the LINE copies; test6 reproduces to 0.1 cm³ |
| | | Stage 0's cube constants corrected from the cardboard cube (14 / 6.3 cm) to the printed one (10 / 5 cm) | Framing only; no volume changes |
| | | `marker_scale_check.py`: scale from the 5 cm ArUco marker edges in VGGT's own point map | Cube-volume scale is within 2–3% on limbs, under 1% on the can. Retracts the earlier "+4.2% scale" term |
| Fri 19 Sep 02:09 | `4fb9e44` | Stage 6 prints the marker scale beside the cube scale and warns above 3% | Fires at 6.0% on the run whose cube fell to the alpha wrap, silent at 2.7% on sound runs |
| Fri 19 Sep 02:42 | `4306baf` | Second MLS pass made the default after a water-truth batch | test5 +24.9% (alpha) to +17.8% (Poisson); 0_right, 1_left, 6_left within 1%; can held |
| Fri 19 Sep 03:12 | `81443a4` | Projected-plane merge defect fixed: a band vanished when its colour fit was gated out; the projected plane now stands in | 0_left 10.1 cm³ sliver to 1773 (water 1800); 2_left +222% to +37%; test6 identical |
| Fri 19 Sep 03:25 | `aeb32a1` | Stage-by-stage inspection of the whole pipeline written up | Lists what can be dropped and four further bugs, below |
| Fri 19 Sep | docs | `docs/` reorganised by purpose, zero broken links | |

## What was tested and ruled out

Each of these was a hypothesis for the over-read. Each was measured, not
reasoned about, and the numbers are in `docs/experiments/2026-09_test_captures/EXPERIMENT_LOG.md`.

- **Reference cube size.** Measured 10.0 cm, marker 5.0 cm. Marker check agrees with the cube scale to 2–3%.
- **Field of view.** VGGT's focal is 2–7% long on leg scenes and 10% long on the can scene; the can scene reads right, so the error does not track the volume error.
- **Camera geometry.** Phone 32 cm above the floor, 6–17° pitch, cube and knee at the same distance.
- **Image resolution.** The phone's HEIC originals (4284 × 5712) make the leg 3–5% fatter than the LINE copies, not thinner.
- **The model.** MapAnything, a different architecture, reads test6's ankle within 1% of VGGT and the knee within 1%. Given the phone's true focal it gets the girth right and the length 14% long, landing on the same +22% volume by a different route.
- **Hair, motion, ring coverage, outlier trimming, reconstruction method.** Ruled out in the previous session; unchanged.

## Numbers as they stand (test6, tape truth 1398.6 cm³ between the bands)

| stage of the week | volume | error |
|---|---|---|
| start of the week | 1939.4 | +38.7% |
| second MLS pass | 1703.9 | +21.8% |
| plus voxel fix, merge fix | 1704.0 | +21.8% |

The remaining error is the leg itself as the model returns it: girth +5% at the ankle rising to +15% at the knee, bands 4–6% further apart than the ruler.

## Open, in priority order

1. **Two captures** decide the remaining cause: test6 with a 30 cm ruler standing beside the bare leg, then the same leg in a patterned stocking. Ten minutes with the phone. No code moves the answer until they exist.
2. **Colour-fit plane normals** can sit up to 51° off the limb and still pass the 35° gate; the cut then slices the band obliquely. Take the normal from the projected plane or the band axis instead.
3. **Reference fill check** at 0.83 is stale and warns on 15 of 22 runs. Re-baseline or retire it in favour of the marker-scale check.
4. **Dead weight to drop** (from the inspection): the duplicate `predictions.npz`, the voxel/warp volume path, Stage 3's unreachable cloud-cut path, the wasted normal estimation in the bottom cap, two legacy tools, `log.csv` in git.
5. **Environment.** A Windows-side process holds 40% of the GPU and makes inference take 8 minutes instead of 46 seconds. The reflective floor destroys captures (5_right, fanta_red); shoot on the matte tile.

## Earlier in September, for context

- 4 Sep: the cut moved from Stage 3's point cloud to Stage 5's watertight solid, and the published scene shows the cut limb (`e671c7a`). A white-and-black band capture was tried and dropped; the bands were re-dyed green.
- 8 Sep: the ground-truth handbook (`docs/guides/measuring_ground_truth.md`, PDF) and the tape-to-volume calculator (`tools/limb_volume_from_tape.py`).
