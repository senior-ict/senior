# Pipeline inspection — 2026-09-19

Scope: the measurement pipeline as it runs from `run.py` (and the same stages
through `stagerun.py`). Every file under `pipeline/`, `run.py`, `stagerun.py`,
`service/jobs.py` and `service/app.py` was read in full, twice, and the five
`vggt/` modules the pipeline imports were read once. The web app is out of
scope (another team's), the rest of `vggt/` was not read, and the docs were
spot-checked rather than audited.

What was run rather than read: every claim about live behaviour below was
checked against the 22 run logs in `~/MU/senior_compare_artifacts/` and the
`output_*/` directories on disk, plus a few direct Python checks noted inline.

## The pipeline as it actually executes

```
 run.py -> orchestrator.main
 0  prep.prepare_frames      GroundingDINO x3 prompts + SAM per frame; ArUco faces;
                             square crop -> 518 px; framing.json, manifest.json
 1  inference.run_inference  VGGT-1B commercial (HF token present); predictions.npz
                             written twice (target/ and 01_inference/)
 2  pointcloud.export_ply    confidence percentile filter; statistical outlier removal
    bands3d                  planes projected from Stage 0's band boxes through the pointmap
 3  clean.clean_and_extract  SOR again; voxel 2 mm; RANSAC floor removal; DBSCAN; box/leg
                             pick; colour marker planes + projected planes merged;
                             ghost voxel / normal filter / MLS 4x / MLS 16x per cluster;
                             RANSAC level; RANSAC upside-down; RANSAC floor; height and
                             axis gates; floor extension; bottom cap; top cap;
                             leg.ply + box.ply; planes published (no cut)
 4  reconstruct              Poisson per object in a subprocess; chi check; alpha ladder fallback
 5  watertight               PyMeshFix repair if open; plane cut on the solid; scene rebuild
 6  volume                   signed volume; cube-volume scale; fill check; marker-scale check;
                             circumference at each plane
```

## Verdict by sub-process

| stage | sub-process | verdict | evidence |
|---|---|---|---|
| 0 | ArUco face homography for the cube box | keep | exact, no model, and it is what the framing gate needs |
| 0 | GroundingDINO "a box." union | keep | documented: faces alone under-cover the cube by 22–90 px |
| 0 | GroundingDINO leg + SAM mask | keep | the crop window needs the limb strip; one call per frame |
| 0 | band detection + colour trace | keep | feeds both the crop and Stage 3's contrast rule |
| 1 | second copy of `predictions.npz` under `target/` | **drop** | 88 MB duplicate, 177 of 257 MB per run; "demo_gradio compatibility" and there is no gradio demo in the repo |
| 2 | confidence percentile filter | keep | |
| 2 | statistical outlier removal | **drop one of the two** | Stage 2 removes 5,440 points, Stage 3's `_load_and_thin` runs SOR again and removes 14,585 more; Stage 2's docstring says "No SOR (Stage 3 applies it)" while doing it |
| 3 | RANSAC ×4 (floor removal, level, upside-down check, floor height) | trim | four fits of the same plane on the same 350–760k cloud; 13.5 s stage total, so cheap, but one fit re-used is simpler |
| 3 | `segment_point_cloud` | **trim** | Stage 3 keeps only `summary["planes"]`; the function also clusters, fits and then *cuts* the cloud with a "marker below 30%" rule whose result is thrown away |
| 3 | colour marker planes (`marker_mask_by_contrast`, HSV fallback) | keep, but see bug 1 | the fallback window fires when the learned contrast is refused |
| 3 | projected band planes (`bands3d`) | keep | the only thing that saved 0_left; its normals are better than the colour fits' |
| 3 | ghost voxel dedup | keep | spacing bug fixed today; it sets the spacing every radius hangs off |
| 3 | normal-aware filter | keep, low value | removes ~3% of points, not load-bearing on volume (its own docstring) |
| 3 | MLS 4x then 16x | keep | validated today on water truth; the 16x pass removes the alpha fallback |
| 3 | height gate, axis gate | keep | fixed today to fall back to the projected twin |
| 3 | floor extension + bottom cap | keep | Poisson needs a closed base; verified working in every log |
| 3 | `cap_point_cloud_bottom` normal estimation | **drop** | it estimates and orients normals over the whole limb (`orient_normals_consistent_tangent_plane(100)`) only to attach normals to the cap; Stage 3 then writes `leg.ply` through trimesh, which drops normals (checked: `leg.ply` has none), and Stage 4's worker re-estimates them anyway |
| 3 | top cap `_close_top` | keep | uncut limb must be closed for Poisson |
| 3 | `apply_cut=True` path: cloud cut, cut-plane caps, `leg_cut.ply`, `merged.ply` | **dead** | both entry points pass `apply_cut=False`; ~100 lines plus `segmentation.apply_marker_cut` are unreachable |
| 4 | Poisson + chi check + alpha ladder | keep | Poisson closes on every validated run now; the ladder is the safety net |
| 4 | reuse of an up-to-date recon mesh | keep | |
| 5 | PyMeshFix repair, plane cut on the solid, scene rebuild | keep | |
| 5 | STL copies of every mesh | trim | four scene files and an STL beside every PLY; nothing in the pipeline reads them |
| 6 | signed volume + cube-volume scale | keep | |
| 6 | warp / voxel / auto-res volume methods, `--voxel-res`, `--no-auto-res` | **drop** | 48 of 48 rows in the `output_*` runs say `watertight`; Stage 5 guarantees a closed mesh or copies the recon; the branch costs a 1.5 s warp import and a GPU context at every Stage 6 |
| 6 | reference fill check (0.83) | **re-baseline or drop** | threshold was set when sound cubes filled 0.87–0.89; the current cleaning gives 0.67–0.79 on sound captures, so it warns on 15 of 22 runs and says nothing. The marker-scale check added today measures the same thing with a physical reference |
| 6 | marker-scale check | keep | fires at 6% on the alpha-cube run, silent at 2.7% on sound ones |
| 6 | circumference at the planes | keep | the one tape-checkable number |
| all | `log.csv` appended on every run | drop from git | tracked, 130 lines, changes on every run |
| tools | `pipeline/tools/com_vol.py`, `pipeline/tools/volume.py` | **drop** | a second Stage 6 with 14 cm defaults and paths (`output_ply/mesh_input.ply`, `segmented_obj.stl`) that no longer exist |
| tools | `viewer.py`, `cut_circumference.py`, `tools/limb_volume_from_tape.py` | keep | |
| vggt | `dependency/`, `heads/track_*`, `utils/visual_track.py` | dead for this repo | tracking and COLMAP export; the pipeline imports six symbols from five modules |

## Bugs found (not yet fixed)

1. **Latent inversion in `core/cluster.py:detect_top_k_objects`.** If a
   cluster's "aruco" score exceeds 0.7, the code labels *that* cluster the
   marker and the *other* one the box. In this pipeline the ArUco cube is the
   box, so the branch would swap the reference and the limb. It has never
   fired: the highest score in 22 runs is 0.57. Legacy from an earlier setup
   with a separate marker. Delete the branch.
2. **Colour-fit plane normals.** `compute_cluster_planes` takes the normal
   from the SVD of the cord's points. On `0_left` the knee band's 144-point
   fit came out 51° from vertical and passed the 35° limb-axis gate because
   the limb itself leans, so the cut slices the band obliquely (40.8 cm girth
   against a 30.0 tape). The projected planes' normals, fitted to the limb
   surface around the band, were 10–16° off. Prefer the projected normal
   when both exist, or take the normal from the axis through the two bands.
3. **Fill-ratio check is stale** (table above). Either measure the sound
   range again with the current cleaning or replace it with the marker-scale
   check.
4. **SOR runs twice** with the docstring claiming it runs once.
5. **`config.py` comments** still say neither cube size has been verified
   with calipers (10.0 was measured today) and that "the ArUco marker is
   identified as the obj cluster". `volume.py`'s docstring says 14 × 14 × 14
   and prints "STAGE 7"; `cluster.py` says 14 cm; `stagerun.floor_planarity`
   converts with 14 / 0.265.

Security: the pipeline runs subprocesses with `sys.executable` and fixed
argument lists, loads the commercial checkpoint with `weights_only=True`,
and uses no `eval`, `pickle` or shell strings. The mechanical scanner reported
one item, `band_planes_from_dirs` never called, which is a false positive
(`stagerun.py:555`). The service's file endpoint maps names through a table and
checks the resolved path stays inside the job directory.

## Documentation

Spot-checked only. Stale: `docs/pipeline/full_flowchart.md`, `docs/archive/2026-08/progress.md`,
`docs/pipeline/mls_explained.md` and `docs/archive/2026-08/experiments/ghost_removal_chain.md` still
carry `GHOST_VOXEL_FACTOR = 0.65`; `README.md` and `docs/pipeline/full_flowchart.md`
describe the 14 cm cube's axis-aligned extents; `docs/pipeline/pipeline_flowchart.md`
still shows the cut inside Stage 3. `docs/archive/2026-08/experiments/scripts_*.py` are
referenced from `FIGURES.md` and were not run.

## Not covered

`web/` (out of scope), `vggt/` beyond the five imported modules, a full
line-by-line audit of the 15 documents, and `service/` beyond confirming it
drives `stagerun.py` with the same flags the CLI uses.
