# Experiment log — 2026-09-04 to 2026-09-18

Every change tried against the volume error, what it was measured against, and
what it did. Nothing here is committed to the pipeline; every row is an
offline experiment on the run outputs, so the pipeline's own numbers are
unchanged throughout. Ground truth is tape unless a row says water.

The one number to keep in mind: on a rigid slim can the pipeline's girth is
**+0.9%** against calipers. Everything above that on a limb is limb, scale, or
wrap — not the model's ability to measure a circumference.

---

## 1. Marker detection

| change | tried on | result | kept? |
|---|---|---|---|
| White and black cords instead of green | `sunshine_v2` | Stage 0 (colour-agnostic detector) boxed both bands on 7/7 frames; Stage 3's colour rule could not separate a neutral cord from skin; every plane rejected, no cut | no — cords re-dyed green |
| Per-band colour instead of one capture average | `sunshine_v2` | Averaging white + black gave grey RGB[71,64,64]; per-band gave RGB[151,140,142] and [41,34,32] | reverted — moot once cords were green |
| Keep the projected plane when its colour twin is later gated out | `sunshine_v2`, cohort 0–6 | Recovered the cut on `sunshine_v2`; on the cohort the same defect had destroyed the lower band on `0_left`, `2_left`, `5_right` (sliver / runaway volumes) | reverted then; **fixed 2026-09-19**, section 11 |
| Drop foot slices from the limb-axis fit | `sunshine_v2` | Real ankle band went from 35.7° (rejected at 35°) to 26.1° | reverted with the above |

## 2. Ground truth

| change | result |
|---|---|
| Water displacement (weigh tub before/after) | Carries two biases: film on the withdrawn limb (+20–50 g, 7–17% of an ankle reading) and fill-level shortfall below the overflow point (−100 cm³ per mm on a leg-sized tub). Used on captures 0–6 and `test5` |
| Circumference tape, disc model, 2 cm spacing | Chosen as primary. Two passes on `test5`: 0.8 cm mean / 2 cm worst on girth, 2 cm on band separation (7% of volume). Water and tape agreed to 4% on `test5` (2070 vs 1985) |
| Two-point cone through the band girths only | Under-reads the segment by 12–22% (misses the calf bulge). Not usable as truth |
| Circle-from-circumference bias | Over-reads area by 1.3% at a/b 1.2, 2.6% at 1.3, 6.3% at 1.5. Limbs measured a/b 1.1–1.5. Handbook corrected from "~2%, constant" |

## 3. Where the error is — per capture

Volumes are the span between the two bands unless noted. "wrap" is the alpha
fallback's inflation, measured directly on `test6`.

| capture | subject | girth err (low / high band) | volume err | alpha fallback | notes |
|---|---|---|---|---|---|
| `test1` | M, hairy | +3.1% / +10.5% | no volume truth | no | four capture styles gave the same error |
| `test2` | M | +6.8% / +14.3% | no volume truth | yes, χ=−2 | worst residual, 4.08 mm |
| `test3` | M | +7.3% / +10.1% | no volume truth | no | cube 10.8 × 10.9 × 10.7 — best cube |
| `test4` | M | +5.3% / +10.9% | no volume truth | no | 100% ring coverage, still +10.9% |
| `test5` | M, hairy shin | +1.5% / +6.7% | **+24.9%** (water 2070) | yes, χ=−4 | profile: shin +19%, calf belly +4% |
| `test6` | nearly hairless | +7.9% / +13.2% | **+38.7%** (tape 1399) | yes, χ=−22 | profile flat +8–12%, no shin spike |
| `fanta_orange` | rigid can | **+0.9%** (calipers 18.5) | +5–10% (height +6.8%) | yes, χ=−12 | girth exact; height is end caps |
| `fanta_red` | can, mirror floor | — | 15,164 cm³ | yes | floor removal took 19.5%; cube fill 0.359 |

`test6` decomposed exactly:

```
cube-derived scale   +4.2% linear   ×1.133    ruler 27.5 vs pipeline 28.7 between bands
residual girth       +5.5%          ×1.114    profile vs tape, scale removed
alpha wrap                          ×1.10     mesh section / points, summed over slices = 1.120
product                             ×1.387    measured +38.7%
```

## 4. Hypotheses tested and ruled out

| hypothesis | test | verdict |
|---|---|---|
| Upper cut plane sits too high | green band located from mesh colour vs plane height | plane within 0.05–0.7 cm of the band on every sound capture. **Wrong** — my own earlier claim |
| Girth over-read comes from incomplete ring coverage | coverage vs error across captures | `test4` at 100% coverage still +10.9%. **Wrong** — my own earlier claim |
| Leg shake during capture | error vs height (−0.32) and vs surface scatter (−0.19); four capture styles agree | anti-correlated with both. **Ruled out** |
| Stray outer points inflate the fitted ring | six trim rules at the band slices | shell is 15 mm thick with an *inward* tail; best rule moved girth 0.4%. **Ruled out** |
| Reconstruction method inflates girth | Poisson vs alpha_shape on `test1` | circumference byte-identical (it is read from the Stage 3 cloud); alpha volume +17% worse. **Ruled out for girth** |
| Vertical blur of the profile | Gaussian blur + gain fit to the tape profile | rms 1.78 → 1.52 cm; systematic +2 cm left on the shin. **Weak, not the cause** |
| Cube is physically ≠ 10 cm | can girth +0.9% on a scene whose cube read 0.815 fill | would have read +4% if the cube were 9.6. **Probably per-scene reconstruction, not the object** — caliper still pending |
| Hair | `test5` (hairy) vs `test6` (nearly hairless) profiles | shin spike +19% present only on `test5`. **Supported** |

## 5. The wrap, seen directly

`ring_gallery.png`: `test6` sliced every 2 cm with the watertight mesh's
cross-section drawn over the cleaned points.

```
 h cm   girth   mesh area / points' ellipse
  0–12  20–27   1.03 – 1.08
 14–28  29–32   1.13 – 1.17    one side carries a second arc ~1 cm inside the
                               outer one; the 30× alpha bridges the outer strays
summed over the span:  1.120   (+12.0% volume from the wrap alone)
```

Poisson tunnelled (χ from −2 to −22) on 5 of 8 runs, which is what forces the
alpha fallback. A finer alpha search between the ladder's rungs found nothing
tighter than the 25× it chose on `test5`.

## 6. MLS radius — the one change that moved the volume

Replays Stage 3's ghost chain from the pre-MLS cluster with only the MLS radius
varied; then re-wraps. The can is the control.

```
                 CAN  (girth 18.5, cylinder ≤ 394.9)      TEST6  (tape 1398.6)
 mls   girth   poisson χ   volume        girth   poisson χ   volume
  0    +0.7%      −6         —           +10.5%     −30         —      (alpha 2141)
  4    +0.5%     −12         —           +10.0%      −6         —      (alpha 1982)  <- pipeline today
  8    +0.6%      −2         —            +9.3%       0         —      (alpha 1780)
 12    +0.6%       2       384.2          +9.2%       2      1606.6    +14.9%
 16    +0.6%       2       385.5          +9.3%       2      1615.7    +15.5%
 24    +1.5%       2       392.0          +0.6%      −2         —      <- artefact, see below
 32    +3.7%       2       407.9         −12.7%     −44         —
```

**12–16× spacing closes Poisson on both objects** — no fallback, no wrap — and
takes `test6` from +38.7% to +15% with the can within 3% of its bound.
**Girth does not move** at any radius up to 16×, which is what a merged
double sheet should do: the merged ring lands between the two sheets, where
the ellipse fit already was. The +15% that remains is cube scale and the real
over-read, now visible instead of buried under the wrap.

The 24× row on `test6` reads +0.6% and looks like a fix. It is not: the can at
the same radius moves the *other* way (+1.5%, then +3.7% at 32×) while `test6`
collapses to −12.7%. Opposite signs on the two objects is distortion crossing
zero by accident.

**Stacked passes** (the pipeline's 4× first, then a wide pass):

```
                 CAN                                  TEST6
 mls    girth   poisson χ   volume        girth   poisson χ   volume
 4→12   +0.6%     −2          —            +9.7%     −4          —
 4→16   +0.6%      2        384.4          +9.6%      2       1614.5   +15.4%
 4→24   +0.6%      2        386.4         +10.0%      2       1632.1   +16.7%
```

Same volume as the single 12–16× pass, same untouched girth — and more
robust: `4→24` holds the can at +0.6% and `test6` at +10.0% where the single
24× pass distorted both. Denoising each sheet first evidently keeps the wide
pass from tearing the surface. **`4→16` is the candidate**: Poisson closes on
both objects, the can lands at 384 against a 395 bound, `test6` goes from
+38.7% to +15.4%, and nothing about the girth is hidden.

What this change does and does not do, stated plainly: it removes the alpha
fallback and its wrap inflation (the ×1.10 term). It does not touch the cube
scale (×1.133) or the residual girth (×1.114), which together are the +15%
that remains. Those need the caliper and a different fix respectively.

**Cold run through the real pipeline** (wired in behind `MLS_SECOND_RADIUS_MULT`,
default off, run with it set to 16; full detail in `COLD_RUN_REPORT.md`):

```
                     today (4×)          cold run (4→16)       truth
 test6  volume       1939.4  +38.7%      1703.9  +21.8%        1398.6 tape
        recon        alpha 30×           Poisson χ=2           
        mesh/pts     1.105               0.989
        girth        20.14 / 32.72       19.95 / 32.09         19.0 / 28.0
 can    volume       415.5               387.2                 ≤ 394.9
        height       15.48  +6.8%        14.78  +1.9%          14.5
        girth        18.45               18.45                 18.5
```

Poisson closed in the pipeline's own path on both objects; the cube was
byte-identical between runs; the offline sweep's per-slice sections matched
the real run to 0.001 but its volume was 5% low. Girth moved about 1% inward.

## 7. Environment failures found along the way

| failure | symptom | cause | fix |
|---|---|---|---|
| Reflective floor | `fanta_red` 15 L "can", cube fill 0.359 | RANSAC removed 19.5% of the floor instead of ~70%; reflections form a second sheet | shoot on the matte tile |
| WSL GPU degraded | inference 14 s → 320–520 s, GPU 100% / 7.9 GB with nothing else on it | not memory, not swap (both checked and wrong at first) | `wsl --shutdown`; it also recovered on its own overnight |
| Background job from another repo | ~2.7 GB RAM held by a headless Blender render | `SCG/auto_entity_extraction` runner, state `T` (suspended) | killed; unrelated to this project |
| Stage 0 refuses a frame | `test5` img7 "cube missing" | cube occluded behind the ankle in that view | correct rejection; ran on the 7 clean frames |

## 8. The cube scale, checked against the 5 cm markers — 2026-09-19

The cube is 10.0 cm and its printed marker 5.0 cm (measured; the cube was 3D
printed). `pipeline/stages/prep.py` still carried the cardboard cube's
`FACE_CM = 14.0, MARKER_CM = 6.3`; corrected to 10.0 / 5.0. Only their ratio is
used, to map a marker's corners out to its face for the Stage 0 crop window
and clipping gate, so the volume never saw those numbers.

The scale itself was then checked a second way (`marker_scale_check.py`): on
every frame VGGT was given, detect the markers, read the predicted 3D point
under each corner, and measure the marker's edges in scene units. 5.0 cm over
that edge is a cm-per-unit that uses no mesh at all.

```
                    marker edge at cube scale     marker scale / cube scale
                    pointmap   depth              linear (pointmap / depth)
 test1               4.85      4.78               1.030 / 1.046
 test2               4.89      4.86               1.023 / 1.028
 test3               4.86      4.84               1.030 / 1.033
 test4               4.95      4.87               1.010 / 1.026
 test5               4.86      4.82               1.029 / 1.038
 test6               4.89      4.88               1.023 / 1.024
 fanta_orange (can)  4.96      4.98               1.008 / 1.005
                     true 5.00
```

The cube-volume scale is not inflated. It reads the marker 1.5–3% **small**
on the limbs and under 1% small on the can, and the marker's vertical and
horizontal edges agree (`test6` 4.91 / 4.92, `test5` 4.85 / 4.86), so nothing is stretched along
one axis. The cube mesh's extents at cube scale are 11.5 × 11.6 × 10.9 cm:
the mesh bloats sideways from the ghost sheets on its faces while its volume
stays near 1000, which is why a volume-derived scale is the more robust of the
two and a face-distance scale would be 15% worse.

This retracts the 2026-09-18 decomposition's "cube-derived scale +4.2%
linear" term. Under the marker scale the numbers get slightly *larger*, not
smaller:

```
                                cube scale      marker scale (pointmap)   truth
 test6  band separation          28.66 cm        29.3 cm                  27.5 ruler
 test6  volume (cold run)        1703.9          ~1805                    1398.6 tape
 can    girth                    18.45           18.6                     18.5
 can    height                   14.78           14.9                     14.5
```

So with the cube at 10.0 and the marker at 5.0 both confirmed, VGGT's own
geometry puts the bands 4–6% further apart than the ruler, and the girth
over-read is the whole remaining error, not a scale term plus a girth term.

One pattern fits all seven captures: the girth error grows with height above
the floor cube — `test6` +5% at the ankle band, +15% at the knee band, and
the same rising shape on `test1`–`test5` — while the rigid can, which stands
on the floor next to the cube and is only 14.5 cm tall, reads within 1–3%.
The reference sits at the floor; the measurement is 20–30 cm above it. Scale
drift with distance from the reference is the open hypothesis. It is testable
with a second known length up at band height (a ruler standing beside the
leg, or the cube raised to the upper band) — a capture, not a code change.

**Field of view, checked against the phone's own lens.** The originals
(`inputs/test6/*.zip`, iPhone 17 main camera, 26 mm equivalent, 4284 × 5712)
give a true focal of 4290 px, which is 518.8 px on the full-width 518 crop
VGGT was fed. VGGT's predicted focal, per frame, against that:

```
 scene         VGGT / true focal      volume error
 test3          1.01 – 1.06  (median 1.037)   girth +7 / +10%
 test5          1.01 – 1.07  (median 1.047)   +24.9%
 test6          1.02 – 1.07  (median 1.037)   +21.8% (cold run)
 fanta_orange   1.08 – 1.18  (median 1.104)   girth +0.9%, height +1.9%
```

VGGT's focal runs 2–7% long on the leg scenes (a narrower field of view than
the lens has) and 10% long on the can scene, assuming the can was shot with
the same lens. The scene with the largest focal error is the one that reads
right, so the focal error does not track the volume error. VGGT takes no
intrinsics as input, so the true focal cannot be supplied to it; a model that
accepts a known field of view would be the way to test this further. Camera
geometry is otherwise ordinary: phone ~32 cm above the floor, 6–17° pitch
down, cube and upper band at the same distance from the camera (ratio 1.07
on `test6`, 1.01 on `test5`).

## 9. The original photos, and the bug they exposed — 2026-09-19

`test6` was re-run from the phone's HEIC originals (4284 × 5712, iPhone 17)
instead of the 1108 × 1477 LINE copies, converted to JPEG in
`inputs/test6_orig/`. Same settings as the cold run (`MLS_SECOND_RADIUS_MULT=16`).

```
                              volume    err     recon (leg / cube)   voxel   leg pts
 LINE copies (cold run)       1703.9   +21.8%   Poisson / Poisson    0.0046  27,244
 originals, same code         1848.9   +32.2%   Poisson / Poisson    0.0079  10,012
```

Worse, and VGGT's geometry had barely moved (marker edge 4.90 both; green band
separation 28.95 vs 28.66; raw-cluster girth at the upper band 33.2 vs 32.3).
The difference was in Stage 3: the denser cloud (762k vs 347k points after
the 2 mm voxel) got a **coarser** ghost voxel, and every radius downstream
(dedup, normal filter, MLS 4× and 16×) hangs off that voxel.

**Root cause** (`pipeline/ghost.py`, `compute_voxel_size`): the "mean
nearest-neighbour distance" was measured on a random 5,000-point sample
*against itself*. That is the sample's spacing, which grows with the square
root of the cloud's size, not the cloud's:

```
                     real spacing   what the code measured   voxel (x0.65)
 LINE copies          0.0016         0.0071                   0.0046
 originals            0.0019         0.0123                   0.0079
```

Fix: build the tree on every point, sample only the queries. `GHOST_VOXEL_FACTOR`
went from 0.65 to 2.8 so the validated runs keep the voxel they had: `test6`
LINE gives 0.0046 exactly as before and reproduces (1704.0 vs 1703.9, Poisson
χ=2 both, girth 19.95 both). The originals now get 0.0054 instead of 0.0079.
Every constant in the ghost/MLS chain was tuned against the inflated value,
which is why the factor is rescaled rather than left at 0.65.

**Originals with the fix**: 1625.0 (+16.2%), leg Poisson χ=2 with 23k points
like the LINE run — but the **cube** fell to the alpha fallback (Poisson
χ=−2) and came out 12.5 × 12.2 × 10.2 cm, so the volume-derived scale is 6%
small (marker edge reads 4.72 at cube scale). That number is a scale
artefact, not an improvement. At the marker scale, which does not depend on
the cube mesh, the three `test6` runs line up:

```
                       cube scale   marker/cube   at marker scale
 LINE copies, fix       1704.0       1.027 lin.    ~1845
 originals, no fix      1848.9       1.020         ~1963
 originals, fix         1625.0       1.060         ~1936
                                                   truth 1398.6
```

**Can control with the fix**: voxel 0.0040 → 0.0045; the cube now closes
under Poisson (χ=2, it had fallen to alpha at χ=0) and measures
10.6 × 10.6 × 10.2 cm; can volume 387.2 → 394.3 against the 394.9 cylinder
bound, height 14.78 → 14.92 (truth 14.5). Control held.

Full-resolution input does not help: VGGT returns a leg 3–5% fatter from
the originals than from the LINE copies, with the same cube. Input pixels
move the answer by a few percent either way; that is the model's noise
floor, and the +30% at marker scale is the same girth over-read as before.

## 10. Second MLS pass validated, now the default — 2026-09-19

Four cold runs through `run.py` with `MLS_SECOND_RADIUS_MULT=16` and the
voxel-spacing fix in, against water truth. test5 needed
`--continue-on-rejected` (one frame has the cube occluded).

```
                truth    before (4x only)           now (4x -> 16x)            girth low / high
 test5   water  2070     2585.3  +24.9%  alpha χ=-4  2438.6  +17.8%  Poisson   22.16 / 34.55  (tape 22 / 32.5)
 0_right water  1830     2485.2  +35.8%  Poisson     2503.9  +36.8%  Poisson   19.98 / 33.30  (20.5 / 29.5)
 1_left  water  1600     2125.8  +32.9%  Poisson     2154.7  +34.7%  Poisson   20.80 / 33.95  (21.5 / 32.0)
 6_left  water  2800     3489.7  +24.6%  Poisson     3507.7  +25.3%  Poisson   23.69 / 39.10  (24.3 / 35.0)
```

Where the fallback used to fire (test5, and test6 and the can in the cold
run) Poisson now closes and the wrap's inflation goes; where it already
closed the pass moves the volume under 1% and the girth under 0.3 cm. The
cube is untouched by it. `MLS_SECOND_RADIUS_MULT` now defaults to 16.
Still owed: a cap in centimetres on the second radius, so a sparser cloud
does not get a physically larger one.

## 11. The projected-plane merge defect, fixed — 2026-09-19

`_merge_projected_planes` kept the colour fit whenever Stage 0's projected
plane agreed with it, and threw the projected plane away. The gates run
later, in levelled space, and the height gate exempts *projected* planes
(a band the detector saw on most photographs is its own corroboration) but
not colour fits. So on a capture whose ankle band sits below one cube
height, the colour fit was rejected, the projected plane that would have
survived was already gone, and the band vanished. With one band left the
span cut ran between the knee band and whatever third plane existed.

Fix: the projected twin rides along as the colour plane's backup. If the
colour fit fails the height gate or the axis gate, the backup takes its
place (for the axis gate, only if it passes the same test). Backups are
stripped before the planes are published.

```
                      before                              after
 0_left  (water 1800)  ankle colour fit rejected, 18% of   colour fit rejected, replaced by the
                       height; cut between knee and a      1,003-pt projected plane; cut ankle to
                       third plane: 10.1 cm³ sliver        knee: 1773.3 cm³ (-1.5%)
 test6   (regression)  1703.998                            1703.996, planes byte-identical
```

The other two captures the defect destroyed, re-run with the fix:

```
                       before (2026-09-04)         after
 2_left  (water 1050)  3381.0  +222%  band lost    1442.0  +37%  both bands; both colour fits
                                                   failed the axis gate (58°, 35°) and the
                                                   projected planes took over; girth 19.05 /
                                                   30.61 against 18.5 / 27.5
 5_right (water 1770)  9337.3  +428%  band lost    8437.8  +377%  both bands found, but the
                                                   capture is a mirror-floor failure: RANSAC
                                                   took 89% of the cloud as floor, 4.5k limb
                                                   points survive, ring coverage 28-46%,
                                                   Poisson balloons. Not a planes problem.
```

The ankle plane after the fix is the projected one (10.3° from vertical,
girth 18.90 against a 20.5 tape). The knee plane is still the colour fit,
144 points with a normal 51° from vertical, which the 35° limb-axis gate
lets through because the limb itself leans; its oblique slice reads 40.8 cm
against a 30.0 tape. That is a separate defect, now on the list.

## 12. TSDF fusion as Stage 2, and the inner-sheet idea — 2026-09-19

Full write-up in `TSDF_STAGE2.md`. Fusing the eight depth maps into one
signed-distance surface (`POINTCLOUD_METHOD=tsdf`, off by default) gives a
cube that fills 0.86 of its box instead of 0.73, a scale within 1% of the
markers, and Poisson closing with no merge pass. The limb does not shrink:
girth at the bands identical to the default path, volume 1686 in an offline
replay and 1778 through `run.py` against 1704 today. The can control failed
on clustering both times. Three other attempts on the same predictions:
picking the inner of the two ghost sheets (confidence does not separate
them; the inner mode sits only 1–2 mm inside the fit and leaves the knee at
+12%), VGGT at 1022 px (breaks: cube fill 0.37), and a perfect cube fitted
to the mesh's faces for scale (6.5% off the marker scale; it would cancel
the leg's error with a manufactured one).

## 13. Still open

- ~~Caliper the cube edge.~~ Done 2026-09-19: cube 10.0, marker 5.0. The
  scale is not the error (section 8).
- **A known length at band height.** Ruler beside the leg or the cube raised
  to the upper band, to test scale drift with distance from the reference.
- **Re-shoot `fanta_red` on the matte tile** with a ruler on the band
  separation — the span-on-a-cylinder test.
- ~~The projected-plane merge defect~~ fixed 2026-09-19 (section 11).
- **Colour-fit plane normals** can be far off the limb (51° on `0_left`'s knee
  band, 144 pts). The cut still lands on the band but slices it obliquely.
- **`1_left` drifted 1.2% between identical runs** on 2026-09-04; `test6`
  reproduced to the byte on 2026-09-18. Not understood.
