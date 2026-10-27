# Restored from the run's own frames

The original photographs of this capture were lost: they were never
committed, while the four other test2 captures were added in 5ab597f on
9 October 2026, and no copy survives anywhere on the machine.

These files were recovered from
`output_4_circumference_calculation_3s/for_debug/00_prep/images/`, which that run wrote
before inference. Stage 0 ran with `vggt_preprocess: pad` and every frame
recorded `mode: original` with a window covering the whole frame, so the
frames were never cropped or resized.

They are pixel-identical to the originals. On `4_circumference_calculation_2c` and
`4_circumference_calculation_1k`, where both the originals and the prep frames survive, all
16 frames match with a maximum channel difference of 0, and the originals
are themselves 1108 x 1477.

The only difference from the lost files is the container: these are PNG
where the originals were JPEG. Re-encoding them as JPEG would add loss
the originals never had, so they are left as PNG under the original
basenames taken from the run's manifest.
