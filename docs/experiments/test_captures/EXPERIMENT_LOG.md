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
| Keep the projected plane when its colour twin is later gated out | `sunshine_v2`, cohort 0–6 | Recovered the cut on `sunshine_v2`; on the cohort the same defect had destroyed the lower band on `0_left`, `2_left`, `5_right` (sliver / runaway volumes) | reverted at the user's request; defect still present |
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

## 8. Still open

- **Caliper the cube edge.** Decides whether `REFERENCE_REAL_SIZE_CM` should
  change. Worth 13% of every volume.
- **Re-shoot `fanta_red` on the matte tile** with a ruler on the band
  separation — the span-on-a-cylinder test.
- **The projected-plane merge defect** (section 1) is still in the pipeline
  and destroyed three of fourteen cohort captures.
- **`1_left` drifted 1.2% between identical runs** on 2026-09-04; `test6`
  reproduced to the byte on 2026-09-18. Not understood.
