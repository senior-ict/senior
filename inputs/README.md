# Captures, and the ground truth each was measured against

The reference these captures are compared with changed four times, and a volume
is only meaningful next to the reference that produced it. A number from one
era cannot be compared with a number from another, so this file records which
capture belongs to which, in order.

The order comes from the filenames. Photographs transferred through LINE are
named `S__<serial>_0.jpg`, and the serial increases with every transfer, so it
orders the sessions reliably even though it is not a date. EXIF timestamps were
stripped in transfer on every folder except `test1_6_orig`, whose photographs
still carry 2026-09-18 and anchor the `test1_*` group.

---

## Era 0 — no ground truth

`small_leg`, `short_leg`, `baam`

The first inputs. There is no reference volume for these, and none was
intended: they existed so the program's output could be looked at, stage by
stage, while the pipeline was being built. **No accuracy claim can be made from
them**, and none is.

They are still cited, for things that need no reference volume. `small_leg`
shows what a centre crop removes from a 2160 x 3840 photograph, which is a
framing observation. `short_leg` is used to compare two reconstruction methods
against each other on the same points, which is a relative comparison.

## Era 1 — water displacement, first procedure

`black shirt`, `blue shirt`, `orange shirt`, `keng`, `champ`, `sunshine`,
`sunshine2`  (serials up to S__119914xxx)

The first attempt at a physical reference. The subject's leg was immersed and
the displaced water weighed.

## Era 2 — water displacement, the 0 to 6 set

`0_left` and `0_right` through `6_left` and `6_right`
(S__120233988 to S__120250418)

Fourteen captures, measured into `groundtruth0-6.csv`. This is the set the
pipeline read 24.6% to 35.8% high against, and the disagreement could not be
attributed: the displacement procedure under-reads when the container is not at
its overflow point, by roughly 100 cm3 per millimetre of shortfall, while the
pipeline over-reads girth where the reconstructed ring is incomplete. Two
mechanisms, opposite directions, neither isolated.

`docs/guides/measuring_ground_truth.md` records both and why the method was
replaced.

## Era 3 — tape measurement, first formula

`test1_1` through `test1_6`, and `test1_6_orig`
(S__120774660 to S__120938508; `test1_6_orig` carries EXIF 2026-09-18)

The move to tape. Circumferences at successive heights, summed as truncated
cones. This removed every error mechanism the water method carried, because
nothing is immersed.

## Era 4 — tape profile, current

`test2_keng`, `test2_champ`, `test2_champ_hairless`,
`test2_sunshine_hairless`  (S__122068997 onward)

The current and most stable reference: a full profile of 27 to 28 readings per
leg rather than a few heights, so the error can be located by height instead of
being summed into one number.

The reference volumes recomputed from these profiles are 1420.2 cm3 for
`test2_keng`, 1981.7 for `test2_champ`, 1954.7 for `test2_champ_hairless` and
1847.1 for `test2_sunshine_hairless`. The profiles are in
`docs/experiments/2026-09_test_captures/*_tape_profile.csv`.

`test2_champ` and `test2_champ_hairless` are the same subject before and after
hair removal, which is what makes them a pair worth reading together.

**`test2_sunshine` is missing.** The run record names
`inputs/test2_sunshine`, 8 photographs beginning `S__122085380_0.jpg`, and that
folder no longer exists; only the 518 px frames inside `output_test2_sunshine`
survive, which are not valid input for a fresh run. Its tape profile is still
on file, so the reference remains even though the capture cannot be repeated.

## Reference objects, no era

`est_325`, `fanta_orange`, `fanta_red`

Rigid objects, not limbs, used as controls. A rigid cylinder cannot move
between photographs, which is what makes `fanta_orange` the control for the
split-surface measurement in
`docs/experiments/2026-10_proposal_evidence/`.

A printed capacity is not an external volume: the 325 ml on a can is what it
holds, not what it displaces, so `est_325` does not carry a usable reference
volume without measuring the can itself.

## Not a capture

`meshy_ai` holds a `.glb` produced by another tool, kept for comparison.
