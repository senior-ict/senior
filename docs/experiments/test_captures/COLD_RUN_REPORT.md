# Cold run with the second MLS pass — 2026-09-18

The stacked-sphere candidate from the sweep, wired into the real pipeline and
run cold on `test6` and the can. Nothing offline this time: both columns in
every gallery are what `run.py` wrote to disk.

## The change

One extra `mls_project` call in `_clean_cluster` (`pipeline/stages/clean.py`)
after the existing 4× pass, limb only, at 16× point spacing. Gated by
`MLS_SECOND_RADIUS_MULT` in `pipeline/config.py`, **default 0 (off)**,
switched on per run with an environment variable:

    MLS_SECOND_RADIUS_MULT=16 python run.py -i inputs/test6

The reference cube is never touched by it, so the scale is identical between
a run with the pass and a run without. The config comment carries the sweep
that justifies the number.

## `test6` — nearly hairless shin, taped every 2 cm

|                      | today (4×)           | cold run (4→16)        | truth |
|---|---|---|---|
| limb volume, span    | 1939.4  **+38.7%**   | 1703.9  **+21.8%**     | 1398.6 (tape) |
| reconstruction       | alpha 30× (Poisson χ=−22) | **Poisson χ=2**, 112,862 faces | |
| mesh / points area   | 1.105                | **0.989**              | 1.00 |
| lower-band girth     | 20.14  (+6.0%)       | 19.95  (+5.0%)         | 19.0 |
| upper-band girth     | 32.72  (+16.9%)      | 32.09  (+14.6%)        | 28.0 |
| cube bbox            | 11.53 × 11.59 × 10.88 | identical             | |
| total time           | 526 s                | 123.5 s                | |

Per slice (`ring_gallery_test6_cold_run.pdf`):

```
 h    today girth  m/p    cold girth  m/p
  0     20.51     1.04      20.67    1.00
  8     23.82     1.06      23.82    1.00
 14     29.39     1.13      29.14    0.99
 20     31.92     1.15      31.54    0.99
 26     30.82     1.17      30.82    0.97
 28     31.93     1.17      31.85    0.98
 mean             1.105                0.989
```

The solid now sits on the points at every height. The volume drops by
1939.4 / 1703.9 = **×1.138**, against the ×1.12 wrap excess measured on the
slices — the fallback's inflation is gone and nothing else moved. The girth
came in about 1% smaller, not larger: the merged ring lands slightly inside
where the two sheets were. That is toward the tape, and small.

## The can — rigid cylinder, calipers 18.5 girth, 14.5 tall

|                      | today (4×)         | cold run (4→16)      | truth |
|---|---|---|---|
| volume               | 415.5              | **387.2**            | ≤ 394.9 (cylinder bound) |
| reconstruction       | alpha (Poisson χ=−12) | **Poisson χ=2**, 53,514 faces | |
| mesh / points area   | 1.003              | 0.999                | |
| girth                | 18.45 (+0.9%)      | 18.45 (+0.9%)        | 18.5 |
| height               | 15.48 (+6.8%)      | **14.78 (+1.9%)**    | 14.5 |
| second pass moved    | —                  | median 0.00035, p95 0.0028 | |

The control held exactly: girth unchanged to the second decimal, and the pass
moved half as much as on the limb because a can has almost nothing to merge.
The height error — +6.8% before — was the alpha end caps; it is +1.9% now,
and the volume sits 2% under the cylinder bound, where a real can with a
domed base and tapered neck belongs.

## What it does and does not do

**Removes**: the alpha-shape fallback and its wrap, on both objects, through
the pipeline's own Poisson and `_survives_repair`. That was the ×1.10 term.

**Leaves**: the cube-derived scale (×1.133 on `test6`; ruler 27.5 cm between
bands, pipeline 28.7) and the real girth over-read (+5% ankle, +15% knee).
Together they are the +21.8% that remains, and no smoothing reaches either.
The caliper on the cube edge is still the single largest lever.

**Offline vs real**: the sweep predicted 1614.5 for `test6`; the real run gave
1703.9. The per-slice sections agree to 0.001, so the 5% sits in what 2 cm
slices do not sample. The real number is the one that counts.

## Validation — done 2026-09-19, pass is now the default

test5 (water 2070): 2585.3 / +24.9% / alpha χ=-4 → 2438.6 / +17.8% / Poisson.
0_right, 1_left, 6_left (water): Poisson before and after, volumes within
1%, girth within 0.3 cm. Table in EXPERIMENT_LOG.md section 10.
`MLS_SECOND_RADIUS_MULT` defaults to 16 in config.py.

## Validation that was owed before it became the default

- `test5` (hairy, noisier shell) and three or four of the 0–6 cohort, with
  their water truth.
- A cap in centimetres, not just spacing multiples: 16× on a sparser cloud is
  a larger physical radius.
- The can re-shot on the matte tile, so the control is not a marginal-cube
  scene (fill 0.815).

## Files

| file | |
|---|---|
| `ring_gallery_test6_cold_run.pdf` | every 2 cm, today vs cold run, from disk |
| `ring_gallery_can_cold_run.pdf` | the same for the can |
| `ring_gallery_two_runs.py` | draws either from two run directories |
| `output_test6_mls16/`, `output_fanta_orange_mls16/` | the runs (local, gitignored) |
