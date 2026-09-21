# Documentation

Start with `../pipeline.md` for what the pipeline does stage by stage. The
rest is grouped by what it is for.

| folder | what is in it | status |
|---|---|---|
| `guides/` | How to measure ground truth with a tape (`measuring_ground_truth.md`, its illustrated PDF, and the script that renders it). | current |
| `pipeline/` | Stage-by-stage flowcharts, the MLS derivation, and the limb skeleton step (`limb_skeleton.md`). | reference; a few numbers lag the code (voxel factor, cube size, the cut now in Stage 5) |
| `experiments/2026-09_test_captures/` | The September test captures against tape truth: the experiment log, the cold-run report, the ring galleries, and the scripts that produced them. `EXPERIMENT_LOG.md` is the running record of everything tried. | current |
| `reviews/` | Whole-repo reviews: the August contract sweep and the 2026-09-19 stage-by-stage inspection. | current |
| `reports/` | Progress reports written for people outside the code. | current |
| `web/` | Running and understanding the web demo. Another team owns the web app. | reference |
| `archive/2026-08/` | The August working notes: progress log, change log against `main`, the experiment ledger, the Stage 6 comparison, and the figures behind them. Superseded by the September work but kept for the derivations. | archived |
| `presentation/` | Meeting decks. | archived |

Conventions: every experiment folder carries the date it was run in its
name; a Markdown document that ships as a PDF keeps the `.md` as the source
and the renderer script beside it.
