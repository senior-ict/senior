# senior-p3 — Limb volume + circumference from phone photos

Senior's photo-to-mesh front half joined to leg-scan-measure's measuring back half,
driven from senior's web app.

```
photos ─► [0] framing gate          senior   00_prep/       frame_NN.png, framing.json
        ─► [1] VGGT inference        senior   01_inference/  predictions.npz
        ─► [2] point cloud           senior   02_pointcloud/ points.ply
        ─► [3] segment + find bands  senior   03_clean/      leg.ply, box.ply, cutting_line_levelled.json
        ─► [4] surface reconstruct   senior   04_recon/      leg_recon.ply, box_recon.ply  (Poisson, still open)
             ── web: review / move the cutting planes ──
        ─► [5] cut                   leg-scan-measure  05_cut/      leg_no_cut.ply, leg_cut_open.ply, cut_planes.json
        ─► [6] fill to watertight    leg-scan-measure  06_fill/     leg_cut.ply, box.ply  (pymeshfix)
        ─► [7] measure               leg-scan-measure  07_measure/  volumes.csv, circumference.csv, measure.json
```

| Stage | Method |
|---|---|
| 0-4 | Unchanged from `senior/` — framing gate, VGGT-1B, confidence-filtered cloud, floor removal + clustering + marker-band planes (slid to inner edge), Poisson reconstruction. |
| 5 cut | leg-scan-measure `planeCut`/`slabCut` ported to Python (`pipeline/core/legscan.py`). Triangles crossing a plane are split exactly; new vertices are shared per edge, so each cut leaves one clean boundary loop. 1 plane keeps what is below, 2 planes keep what lies between. Largest piece kept. |
| 6 fill | `pymeshfix` closes the cut ends and Poisson holes into one watertight solid (keep main piece, no join — leg-scan-measure defaults). Reference cube closed the same way. Guard: if `repair()` throws away geometry (it does on very regular meshes), falls back to `fill_holes()`. |
| 7 measure | Volume = signed tetrahedra `Σ a·(b×c)/6`, float64. Scale from the cube: `k = 10³ / V_box`, `cm/unit = k^(1/3)`. Circumference at each cut = plane ∩ uncut surface, longest closed loop, **tape = convex hull perimeter**, plus outline length and area. If the raw surface has a gap at the plane, the filled solid is sliced 1 mm inside the cut instead (reported as `source`). |

Checks: synthetic cylinder slab cut + fill reads 0.000% volume error (straight and 15° tilted
cuts); sphere slab −0.04%; tilted-cylinder circumference 324.317 vs 324.319 mm ellipse.
On a real senior capture, stages 5-7 give 3400.37 cm³ vs senior's own cut-after-watertight
3401.50 cm³ (0.03%).

## Run

Same environment as senior (`~/miniconda3/envs/senior`, see `requirements.txt`).

```bash
python run.py -i inputs/5_circumference_calculation_1k          # stages 0-7, detected planes
python stagerun.py 0-4 -i inputs/<capture> --name job           # front half
python stagerun.py 5-7 --name job --planes my_planes.json       # re-cut in seconds
python stagerun.py 5-7 --name job --no-cut                      # publish uncut limb, measure cube only
```

Stage 6 flags: `--meshfix-join` (join nearby pieces), `--meshfix-keep-all` (keep every piece).
Old 14 cm cube captures: `REFERENCE_REAL_SIZE_CM=14`.

## Web app

```bash
cd web && npm install      # first time
./serve.sh                 # web http://localhost:3111, api :8000
```

Flow (as senior): Upload → Framing (stage 0) → Processing (stages 1-7 with `--no-cut`: limb
reconstructed but not cut, cube measured for scale) → **Review** (drag the planes; circumference
at each plane updates live using leg-scan-measure's surface slice, ported to
`web/src/lib/meshslice.ts`) → confirm → stages 5-7 re-run → **Result** (volume, closed-solid
check, circumference at both cuts, .ply/.stl download).

## Layout

```
pipeline/core/legscan.py           ported leg-scan-measure maths (cut, slice, hull, volume, pymeshfix)
pipeline/stages/cut.py             Stage 5
pipeline/stages/fill_watertight.py Stage 6
pipeline/stages/measure.py         Stage 7
stagerun.py / run.py               stage runner / end-to-end orchestrator
service/                           FastAPI job service (run 1-7, recut 5-7)
web/                               Next.js app (senior's, rewired)
(sources: ../senior, ../leg-scan-measure)
README.senior.md, pipeline.md      senior's original docs (stages 0-4 still accurate)
```
