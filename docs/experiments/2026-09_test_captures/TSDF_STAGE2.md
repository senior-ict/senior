# TSDF fusion as Stage 2 — 2026-09-19

`POINTCLOUD_METHOD=tsdf` (config, environment, or `--pointcloud-method tsdf`
on `run.py` and `stagerun.py`). Off by default. Code: `pipeline/core/tsdf.py`,
the branch in `pipeline/stages/pointcloud.py`, and a `merge_ghost_sheets`
switch in Stage 3 that turns the wide second MLS pass off for fused clouds.

## What it does

The default Stage 2 stacks every frame's pointmap; the views disagree by up
to a centimetre about where the skin is, and every placement is kept, which
is the ghost double sheet Stage 3's ghost voxel, normal filter and two MLS
passes exist to collapse. Fusion integrates each frame's depth map into a
truncated signed-distance volume with VGGT's own poses and intrinsics, so
the views average to one surface before Stage 3 sees them.

Three details it needed to work inside the real pipeline:

- **Voxel size in centimetres** before Stage 6 has a scale: taken from the
  5 cm ArUco marker edges in the raw point map (`marker_scale.py`), which
  needs no mesh. 3 mm; 1.5 mm gave ten times the points and Stage 3's MLS
  loop took most of an hour on the cube alone.
- **Support filter.** The depth head and the pointmap agree per pixel, and
  both reach four units out. What trims the default cloud is the spatial
  outlier removal, which deletes far surfaces because they are sparse. A
  TSDF densifies those same walls onto a regular grid, nothing deletes
  them, and DBSCAN clustered the room (first run: leg 33 L). Fused points
  now survive only within three voxels of a point the default path kept.
- **No second MLS pass.** Stage 3's radii are multiples of point spacing;
  the fused cloud is sparser, so the 16x pass became a 5.5 cm ball and
  crushed the cube (fill -0.27). A fused cloud has one sheet, so the pass
  is skipped for it.

## Results

```
                                  default        TSDF, fork replay   TSDF, main pipeline
 test6 volume between bands       1704.0 +21.8%  1686.4 +20.6%       1777.6 +27.1%
 girth low / high (tape 19/28)    19.95 / 31.85  19.57 / 30.96       19.95 / 32.00
 profile mean error (tape)        +7.3%          +5.8%               not measured
 cube fill (sound 0.87-0.89)      0.733          0.866               0.859
 cube, cm                         11.7x11.2x10.7 10.8x10.5x10.9      10.9x10.9x10.6
 marker / cube scale              1.027          1.018               1.007
 leg recon                        Poisson        Poisson             Poisson
 can control                      387 / +0.9%    clustering merged   clustering merged
                                                 floor into the can  the can into the cube
```

The "fork replay" ran the fusion on the saved predictions with a hand-given
scale and the second pass off; the "main pipeline" column is `run.py`
end to end with the flag. They differ by 5% on the volume, which is the
fusion's sensitivity to its confidence cut and support filter, and that
alone says it is not a stable improvement yet.

## Verdict

What fusion delivers, reproducibly: a reference cube that reconstructs as
a cube (fill 0.86–0.87 against 0.73), a scale that agrees with the markers
to under 1%, one surface instead of two, Poisson closing with no merge pass
and no alpha fallback. Those are real and they simplify Stage 3.

What it does not deliver: a smaller limb. The girth at the bands is the
same as the default path's, and the volume moved +1% one way in the replay
and +5% the other way in the pipeline. A bias every view shares averages
to itself. The can control fails on both attempts for a different reason
each time, clustering, because the fused cloud's density and continuity
are not what `detect_top_k_objects` was tuned on.

Stays off by default. To adopt it, Stage 3's clustering has to be re-tuned
for fused clouds and the cohort run against water, the same bar the second
MLS pass cleared. The regression run of the default path reproduced
1703.998, so the flag costs nothing while off.
