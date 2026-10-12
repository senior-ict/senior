# Pad the photo, do not crop it — 2026-09-21

`config.FRAME_FIT` now defaults to `"pad"`: Stage 0 still gates every frame,
learns the band colour and finds the band boxes, but it no longer crops.
Each photo goes to VGGT whole, and VGGT's own loader shrinks it to fit
518 px and pads it with white to a square. Stage 2 drops the points VGGT
predicts on the white padding; `core/bands3d.py` maps band boxes through
the padding. `--frame-fit crop` restores Stage 0's sliding square crop.

## Why

VGGT assumes every frame's optical centre is the middle of the image. Stage
0's crop was a full-width square slid up or down to hold the cube and the
bands, which put the photo's real centre 19–74 px (of 518) below the middle,
differently on every frame. VGGT reconciles that by distorting the whole
scene: on test6 the leg came out 10% too long and 7% too fat against the
ruler and the tape. An earlier per-frame check could not see it, because the
distortion is scene-wide rather than per frame; running VGGT on the original
photos, padded or centre-cropped, showed it directly (the fork's
`docs/experiments/model_swap/CROP_TEST.md`).

`prep.py` records that padding was tried before the crop was chosen and set
aside partly because "the limb lost 11% of its volume". There was no ground
truth then; that was the volume moving toward it.

## Results, full pipeline end to end

```
 capture   truth              sliding crop       padded
 test6     1398.6 tape        1704  +21.8%       1500   +7.3%
 test5     2070   water       2439  +17.8%       2167   +4.7%
 0_right   1830   water       2504  +36.8%       1731   -5.4%
 1_left    1600   water       2155  +34.7%       1599   -0.0%
 6_left    2800   water       3508  +25.3%       2647   -5.5%
 2_left    1050   water       1442  +37.3%       1168  +11.2%
 mean |error|                 29.0%              5.7%
 mean signed error            +29.0%             +2.0%
```

Poisson closed on every leg. On test6 the remaining +7% is mostly length
(band separation 28.87 cm against the ruler's 27.5; girth +1.7%), which may
partly be where the band is measured from: the cut is at the cord's centre.

The can (control): 394 -> 354 cm³, height 14.9 -> 14.1 (truth 14.5). Its
cube fell to the alpha fallback on this run (Poisson chi=-2), which moves
the scale, so the can is not a clean control this time. Re-run it before
reading anything into the drop.

The Stage 6 marker-scale check was removed in the same change: on the padded
test6 run the ruler agreed with the cube (length +5.0%) and not the markers
(+8.8%), and the markers' 3D corners come from VGGT's points at the busiest
texture in the frame.
