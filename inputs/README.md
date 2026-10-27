# Captures, and the ground truth each was measured against

The reference these captures are compared with changed several times, and a
volume is only meaningful next to the reference that produced it. A number from
one era cannot be compared with a number from another, so this file records
which capture belongs to which, in order.

## How a folder is named

    <era>_<reference method>_<subject id>[_hairless]

The leading number is the era, which fixes the reference method the capture was
measured against. The subject id counts subjects within that era, and carries a
letter where the subject is known: `k` for Keng, `c` for Champ, `s` for
Sunshine. Two captures of one leg before and after hair removal share an id and
differ only by the `_hairless` suffix, which is what makes them a pair worth
reading together.

Era 2 captures both legs of each subject, so its ids carry `_left` or `_right`
instead of a subject letter.

Six eras, in time order: era 0 has no reference at all, eras 1 to 3 were
measured by water displacement, and eras 4 and 5 by circumference.

The order within an era comes from the filenames. Photographs transferred
through LINE are named `S__<serial>_0.jpg`, and the serial increases with every
transfer, so it orders the sessions reliably even though it is not a date. EXIF
timestamps were stripped in transfer on every folder except
`4_circumference_calculation_1k_orig`, whose photographs still carry 2026-09-18
and anchor that group.

---

## Era 0 — no ground truth

`0_first_sample_1`, `0_first_sample_2`, `0_first_sample_3`

The first inputs. There is no reference volume for these, and none was
intended: they existed so the program's output could be looked at, stage by
stage, while the pipeline was being built. **No accuracy claim can be made from
them**, and none is.

They are still cited, for things that need no reference volume.
`0_first_sample_3` shows what a center crop removes from a 2160 x 3840
photograph, which is a framing observation. `0_first_sample_2` is used to
compare two reconstruction methods against each other on the same points,
which is a relative comparison.

## Era 1 — water displacement, first procedure

`1_water_displacement_1k`, `1_water_displacement_2c`,
`1_water_displacement_3s`, `1_water_displacement_4`,
`1_water_displacement_5`, `1_water_displacement_6`
(serials up to S__119914xxx)

The first attempt at a physical reference. The subject's leg was immersed and
the displaced water weighed.

Ids 1 to 3 are the named subjects. Ids 4 to 6 were recorded only by the shirt
the subject wore — black, blue and orange in that order — so no subject letter
can be given for them.

A seventh era 1 capture existed: a second capture of Sunshine, which failed and
was removed rather than kept as an input nothing should be run on. The shirt
ids were closed up over the gap it left, so no id is vacant. Two code comments
still cite what was measured on that capture — the band under-count case in
`pipeline/stages/clean.py` and the second-box threshold in
`pipeline/stages/prep.py` — and they describe it rather than name a folder that
is gone.

## Era 2 — water displacement, the fourteen-capture set

`2_water_displacement_1_left` and `2_water_displacement_1_right` through
`2_water_displacement_7_left` and `2_water_displacement_7_right`
(S__120233988 to S__120250418)

Fourteen captures, seven subjects, both legs of each. They are measured into
`groundtruth0-6.csv`, whose `no` column still counts from zero, so **subtract
one from the folder id to find the row**: `2_water_displacement_1_left` is row
`no = 0`, column `left_vol`, and `2_water_displacement_7_right` is row
`no = 6`, column `right_vol`.

None of the seven is Keng, Champ or Sunshine, which is why these ids carry no
subject letter. The CSV records only sex: five W, two M.

This is the set the pipeline read 24.6% to 35.8% high against, and the
disagreement could not be attributed: the displacement procedure under-reads
when the container is not at its overflow point, by roughly 100 cm3 per
millimeter of shortfall, while the pipeline over-reads girth where the
reconstructed ring is incomplete. Two mechanisms, opposite directions, neither
isolated.

`docs/guides/measuring_ground_truth.md` records both and why the method was
replaced.

## Era 3 — water displacement, the confirmed pose

`3_water_displacement_1c`  (S__120897540 onward)

One capture, of Champ, in the pose chosen for every capture after it. Its
reference is water displacement, at 2070 cm3.

**It also carries a circumference reading**, taken after the water reading in
order to check the water against something that shares none of its error
mechanisms. That cross-check is what moved the project to circumference, so
this capture sits in the water era but is where the next two come from.

Four captures preceded it, which existed only so the pose could be chosen and
carried no reference volume of any kind. They were removed once the pose was
settled; they are in the history if they are ever wanted.

Hair is not a confound here. Water submerges hair rather than compressing it,
and wet hair lies flat against the leg, so this capture needed no shaving even
though the leg was unshaved.

## Era 4 — circumference, first formula

`4_circumference_calculation_1k`, and `4_circumference_calculation_1k_orig`,
which is the same capture before LINE stripped its EXIF
(S__120938501 onward; the `_orig` folder carries EXIF 2026-09-18)

Keng, measured by tape at successive heights and summed as truncated cones, at
1398.6 cm3. This removed every error mechanism the water method carried,
because nothing is immersed.

## Era 5 — circumference profile, current

`5_circumference_calculation_1k`, `5_circumference_calculation_2c`,
`5_circumference_calculation_2c_hairless`, `5_circumference_calculation_3s`,
`5_circumference_calculation_3s_hairless`  (S__122068997 onward)

The current and most stable reference: a full profile of 27 to 28 readings per
leg rather than a few heights, so the error can be located by height instead of
being summed into one number.

The reference volumes recomputed from these profiles are 1420.2 cm3 for
`5_circumference_calculation_1k`, 1981.7 for `5_circumference_calculation_2c`,
1954.7 for `5_circumference_calculation_2c_hairless`, 1831.2 for
`5_circumference_calculation_3s` and 1847.1 for
`5_circumference_calculation_3s_hairless`. The profiles are in
`docs/experiments/2026-09_test_captures/*_tape_profile.csv`.

Two pairs read before and after hair removal: `2c` with `2c_hairless`, and `3s`
with `3s_hairless`. Unlike era 3, a circumference reading compresses hair while
a photograph records its outer surface, so the band region is shaved before
capture.

`5_circumference_calculation_3s` was recovered rather than kept. Its original
folder was lost, and the eight photographs in it were restored from the 518 px
frames the run had written; `5_circumference_calculation_3s/RESTORED.md`
records how, and the recovery was checked as pixel-identical on the captures
where both copies survive.

`5_circumference_calculation_3s_hairless` holds seven photographs, not eight.
That is the capture itself, not a frame that was dropped.

One frame of `5_circumference_calculation_2c_hairless` shows no reference cube,
which the current pipeline's framing stage refuses. See
`docs/experiments/2026-10_proposal_evidence/STAGE0_GATE_REFUSAL.md`.

## Reference objects, no era

`est_325`, `fanta_orange`, `fanta_red`

Rigid objects, not limbs, used as controls, and named for the object rather
than an era because they carry no leg and no era's reference applies to them. A
rigid cylinder cannot move between photographs, which is what makes
`fanta_orange` the control for the split-surface measurement in
`docs/experiments/2026-10_proposal_evidence/`.

A printed capacity is not an external volume: the 325 ml on a can is what it
holds, not what it displaces, so `est_325` does not carry a usable reference
volume without measuring the can itself.
