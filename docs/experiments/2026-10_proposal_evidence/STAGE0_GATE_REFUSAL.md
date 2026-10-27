# The framing gate refuses a capture that meets its own minimum

`4_circumference_calculation_2c_hairless` is eight photographs. Stage 0 refuses
the whole capture because one of them does not show the reference cube.

`stage0_gate_refusal.log` is the run, on all eight frames:

    S__122134535_0.jpg -> frame_02.png   REJECT  [very crucial]
      cube missing — the scale cannot be recovered

    STAGE 0 VERDICT: 7 pass, 0 warning, 1 reject  (of 8 submitted)
    STAGE 0: INPUT NOT ACCEPTED — please re-take and re-submit
      7 of 8 frames usable; 6 are required.

The last line is the point. The stage states that seven frames are usable and
that six are required, and then refuses the input anyway. The rule is in
`pipeline/stages/prep.py`:

    elif not cube_seen:
        escalate(REJECT, "cube missing — the scale cannot be recovered", ...)

A frame-level REJECT fails the run regardless of how many frames passed.

## Why the rule is wrong as written

Scale is recovered from the cube reconstructed across the whole set, not from
any one frame. A frame without the cube contributes no cube points, so it costs
nothing; discarding it removes a real viewpoint of the limb, which does cost
something. Some camera angles cannot show the whole cube at all.

## How the reported figure was produced

The −3.47% in the proposal's table 5.1 is this capture run on its seven passing
frames — that is, the eight photographs with `S__122134535_0.jpg` excluded. To
repeat it, run the capture with that one file held out. `--continue-on-rejected`
is not equivalent: it runs on all eight, including the frame with no cube.

## What would settle the replacement rule

How many frames must show the cube is not measured. It could be established by
dropping cube-bearing frames one at a time from a capture that works and
watching the fitted cube side and the reported volume move.
