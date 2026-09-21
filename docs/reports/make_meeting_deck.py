"""Build the 21 September 2026 meeting deck as a PDF (16:9 slides, matplotlib only).

    python docs/reports/make_meeting_deck.py

Every number here is copied from a run log or a write-up in docs/; the source
is named next to each table in the deck.
"""
import pathlib

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

OUTPUT = pathlib.Path(__file__).resolve().parent / "2026-09-21_meeting_deck.pdf"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
TAPE_PROFILE_PATH = PROJECT_ROOT / "docs/experiments/2026-09_test_captures/test6_tape_profile.csv"
TEST6_TAPE_VOLUME_CM3 = 1398.6

SLIDE = (13.33, 7.5)
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8882"
SURFACE = "#fcfcfb"
RULE = "#e4e2dc"
HIGHLIGHT = "#eaf2fc"
VERSION_COLOURS = {"v3": "#c9c7c0", "v4 mid": "#8fb8ea", "v4 final": "#2a78d6"}
TAPE_COLOUR = INK


def new_slide(title, subtitle=None):
    """A blank slide with its title and optional subtitle; returns the figure."""
    figure = plt.figure(figsize=SLIDE, facecolor=SURFACE)
    figure.text(0.05, 0.92, title, fontsize=24, weight="bold", color=INK, va="top")
    if subtitle:
        figure.text(0.05, 0.855, subtitle, fontsize=13, color=INK_SECONDARY, va="top")
    return figure


SLIDE_COUNTER = {"number": 1}


def footer(figure, source=None):
    """The next slide number and, when given, the source of the slide's numbers."""
    SLIDE_COUNTER["number"] += 1
    figure.text(0.95, 0.035, str(SLIDE_COUNTER["number"]), fontsize=10, color=INK_MUTED, ha="right")
    if source:
        figure.text(0.05, 0.035, f"Source: {source}", fontsize=9, color=INK_MUTED)


def draw_table(figure, rectangle, header, rows, column_widths, highlight_rows=(), font_size=11,
               bold_columns=()):
    """A clean table: header in bold, thin rules between rows, optional row highlight."""
    left, bottom, width, height = rectangle
    axes = figure.add_axes([left, bottom, width, height])
    axes.axis("off")
    row_count = len(rows) + 1
    row_height = 1.0 / row_count
    positions = [0.0]
    for column_width in column_widths[:-1]:
        positions.append(positions[-1] + column_width)
    for row_index in range(row_count):
        top = 1.0 - row_index * row_height
        if row_index - 1 in highlight_rows:
            axes.add_patch(plt.Rectangle((0, top - row_height), 1, row_height, color=HIGHLIGHT, lw=0))
        cells = header if row_index == 0 else rows[row_index - 1]
        for column_index, cell in enumerate(cells):
            is_header = row_index == 0
            axes.text(positions[column_index] + 0.008, top - row_height / 2, str(cell),
                      fontsize=font_size, va="center", ha="left",
                      weight="bold" if is_header or column_index in bold_columns else "normal",
                      color=INK if is_header else INK_SECONDARY if column_index == 0 else INK)
        axes.axhline(top - row_height, color=INK if row_index == 0 else RULE,
                     lw=1.2 if row_index == 0 else 0.8)
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)


def bullet_list(figure, left, top, lines, font_size=14, spacing=0.062):
    """Plain bullets, one line each; a line starting with two spaces is a sub-point."""
    y_position = top
    for line in lines:
        if line.startswith("  "):
            figure.text(left + 0.025, y_position, "–  " + line.strip(), fontsize=font_size - 2,
                        color=INK_SECONDARY, va="top")
        else:
            figure.text(left, y_position, "•  " + line, fontsize=font_size, color=INK, va="top")
        y_position -= spacing


def slide_title(pdf):
    """Opening slide."""
    figure = plt.figure(figsize=SLIDE, facecolor=SURFACE)
    figure.text(0.07, 0.62, "Limb-segment volume from phone photos", fontsize=34, weight="bold", color=INK)
    figure.text(0.07, 0.53, "Four versions of the pipeline, what went wrong, and what fixed it",
                fontsize=18, color=INK_SECONDARY)
    figure.text(0.07, 0.36, "Mean error between the two bands, six captures with ground truth",
                fontsize=14, color=INK_SECONDARY)
    figure.text(0.07, 0.24, "31%", fontsize=64, weight="bold", color=VERSION_COLOURS["v3"])
    figure.text(0.24, 0.27, "→", fontsize=40, color=INK_MUTED)
    figure.text(0.31, 0.24, "5.7%", fontsize=64, weight="bold", color=VERSION_COLOURS["v4 final"])
    figure.text(0.07, 0.17, "v3 (cut at Stage 5), sound runs only          v4, today (padded photos)",
                fontsize=12, color=INK_MUTED)
    figure.text(0.07, 0.07, "Senior project meeting  ·  21 September 2026", fontsize=12, color=INK_MUTED)
    pdf.savefig(figure)
    plt.close(figure)


def slide_versions(pdf):
    """The four pipeline versions side by side."""
    figure = new_slide("Four versions of the pipeline",
                       "Same idea throughout: 8 phone photos + 10 cm ArUco cube → VGGT 3D points → mesh → volume")
    versions = [
        ("v1  Old", "main branch",
         ["VGGT centre-crops each photo", "Floor removal, DBSCAN", "Cut the point cloud at the marker",
          "Alpha / Poisson mesh", "Volume: watertight, or voxel", "  flood-fill when the mesh leaks",
          "One band only: measures below it"]),
        ("v2  Reworked + Stage 0", "12–24 Aug",
         ["Stage 0: find cube, limb, bands", "  (GroundingDINO + SAM), gate", "  bad photos, crop around them",
          "Learned band colour", "Floor, marker, cut-rule fixes", "Poisson with alpha fallback",
          "Web review before the cut"]),
        ("v3  Cut at Stage 5", "31 Aug",
         ["Cut the watertight mesh, not", "  the point cloud", "Two bands: measure between them",
          "Reviewer places the cut on a", "  surface in the web app", "Cohort 0–6 + test captures",
          "  measured against water / tape"]),
        ("v4  Current", "18–21 Sep",
         ["Second, wider MLS pass", "Ghost-voxel spacing bug fixed", "Projected band plane as backup",
          "Pad the whole photo; Stage 0", "  no longer crops", "Marker-scale check removed",
          "TSDF fusion: optional, off", "Limb skeleton: smooth rings"]),
    ]
    column_width = 0.215
    for index, (name, when, lines) in enumerate(versions):
        left = 0.05 + index * (column_width + 0.018)
        is_current = index == 3
        box = FancyBboxPatch((left, 0.13), column_width, 0.66, boxstyle="round,pad=0.005,rounding_size=0.01",
                             transform=figure.transFigure, facecolor=HIGHLIGHT if is_current else "white",
                             edgecolor=VERSION_COLOURS["v4 final"] if is_current else RULE, linewidth=1.5)
        figure.patches.append(box)
        figure.text(left + 0.012, 0.765, name, fontsize=14, weight="bold", color=INK, va="top")
        figure.text(left + 0.012, 0.715, when, fontsize=11, color=INK_MUTED, va="top")
        y_position = 0.655
        for line in lines:
            indent = 0.02 if line.startswith("  ") else 0.0
            figure.text(left + 0.012 + indent, y_position, line.strip(), fontsize=11.5,
                        color=INK_SECONDARY if indent else INK, va="top")
            y_position -= 0.066
    footer(figure, "git history; docs/pipeline/; docs/experiments/")
    pdf.savefig(figure)
    plt.close(figure)


STAGES = ["0  Framing", "1  VGGT", "2  Point cloud", "3  Clean", "4  Mesh", "5  Cut", "6  Volume"]
CHANGES = {
    0: "gates as before;\nno longer crops",
    1: "whole photo,\npadded square",
    2: "drops the\nwhite padding",
    3: "spacing fix;\n2nd MLS pass;\nband backup",
    6: "cube scale only;\nmarker check\nremoved",
}


def slide_v3_v4_glance(pdf):
    """Two rows of stage boxes, v3 above v4, the changed stages highlighted."""
    figure = new_slide("From v3 to v4 at a glance", "Same seven stages; blue marks what changed")
    box_width = 0.1
    gap = 0.013
    for row_index, (label, top) in enumerate((("v3  reworked\n(cut at Stage 5)", 0.7), ("v4  current", 0.44))):
        figure.text(0.04, top - 0.055, label, fontsize=12, weight="bold", color=INK, va="center")
        for stage_index, stage in enumerate(STAGES):
            left = 0.18 + stage_index * (box_width + gap)
            changed = row_index == 1 and stage_index in CHANGES
            box = FancyBboxPatch((left, top - 0.11), box_width, 0.11,
                                 boxstyle="round,pad=0.003,rounding_size=0.008", transform=figure.transFigure,
                                 facecolor=VERSION_COLOURS["v4 final"] if changed else "white",
                                 edgecolor=VERSION_COLOURS["v4 final"] if changed else RULE, linewidth=1.3)
            figure.patches.append(box)
            figure.text(left + box_width / 2, top - 0.055, stage, fontsize=12, ha="center", va="center",
                        color="white" if changed else INK, weight="bold" if changed else "normal")
            if changed:
                figure.text(left + box_width / 2, top - 0.13, CHANGES[stage_index], fontsize=9.5,
                            ha="center", va="top", color=INK_SECONDARY)
    figure.text(0.18, 0.19, "v3 Stage 0 cropped each photo to a square that slid to fit the cube and bands.",
                fontsize=13, color=INK)
    figure.text(0.18, 0.15, "That moved the optical centre off the middle, and VGGT distorted the whole scene.",
                fontsize=13, color=INK)
    figure.text(0.18, 0.11, "v4 hands VGGT the whole photo instead. That one change is most of the gain.",
                fontsize=13, color=INK, weight="bold")
    footer(figure, "git log 18–21 Sep, keng-branch")
    pdf.savefig(figure)
    plt.close(figure)


def slide_v3_v4_stages(pdf):
    """Stage-by-stage: what v3 did, what v4 does, why."""
    figure = new_slide("From v3 to v4, stage by stage", "Only the stages that changed; Stages 4 and 5 are the same code")
    header = ["Stage", "v3  (reworked)", "v4  (current)", "Why"]
    rows = [
        ["0  Framing", "Find cube, limb, bands; gate;\ncrop a sliding square around them", "Find, gate, learn band colour\nas before; pass the photo whole",
         "The slide put the optical centre\n19–74 px off the middle"],
        ["1  VGGT", "Gets Stage 0's 518 px crop", "Gets the whole photo, shrunk\nand padded to 518 px",
         "VGGT assumes the centre is\nthe middle of the image"],
        ["2  Point cloud", "Every confident pixel", "Also drops the white padding", "Padding has no geometry"],
        ["3  Clean", "Ghost voxel sized by a buggy\nspacing; one MLS pass (4x);\nlost band if colour fit failed",
         "Spacing fixed; 2nd MLS pass\n(16x) merges the double skin;\nprojected plane as backup",
         "Poisson closes instead of the\nalpha wrap; bands no longer\nvanish"],
        ["6  Volume", "Cube-volume scale", "Cube-volume scale\n(marker check tried, removed)", "Ruler agreed with the cube"],
    ]
    draw_table(figure, (0.05, 0.1, 0.90, 0.72), header, rows, [0.14, 0.28, 0.28, 0.30], font_size=11)
    footer(figure, "PAD_NOT_CROP.md; EXPERIMENT_LOG.md sections 6–13")
    pdf.savefig(figure)
    plt.close(figure)


def slide_v3_v4_effects(pdf):
    """Each change on its own and what it did, measured."""
    figure = new_slide("Each v4 change, and what it did", "Volume between the bands against tape / water; changes applied in order")
    header = ["Change", "test6 (tape)", "test5 (water)", "Cohort (water)"]
    rows = [
        ["v3 starting point", "+38.7%  (alpha wrap)", "+24.9%  (alpha wrap)", "+25 to +36%;  2_left +222%"],
        ["+ 2nd MLS pass", "+21.8%  Poisson closes", "+17.8%  Poisson closes", "within 1% of v3 where\nPoisson already closed"],
        ["+ ghost-voxel spacing fix", "+21.8%  (unchanged)", "—", "stops denser photos\nbeing cleaned coarser"],
        ["+ band-plane backup", "unchanged", "unchanged", "0_left 10 cm³ → −1.5%\n2_left +222% → +37%"],
        ["+ pad, do not crop", "+7.3%", "+4.7%", "−5.5% to +11.2%\nmean |error| 29% → 5.7%"],
    ]
    draw_table(figure, (0.05, 0.14, 0.90, 0.66), header, rows, [0.24, 0.23, 0.23, 0.30], highlight_rows=(4,),
               font_size=12)
    figure.text(0.05, 0.08, "The MLS pass and the two bug fixes made the mesh sound; padding removed the systematic bias.",
                fontsize=12.5, color=INK_SECONDARY)
    footer(figure, "run logs 18–21 Sep")
    pdf.savefig(figure)
    plt.close(figure)


def slide_problems(pdf):
    """Problems met in v3/v4 and how each was solved."""
    figure = new_slide("Problems we hit, and how we solved them", "v3 → v4, measured against tape and water at each step")
    header = ["Problem", "Cause we found", "Fix", "Effect (measured)"]
    rows = [
        ["Alpha fallback\ninflated the volume", "Double 'ghost' skin 1 cm apart;\nPoisson tunnels, falls back", "2nd MLS pass (16x)\nmerges the two skins", "test6 +38.7% → +21.8%\ntest5 +24.9% → +17.8%"],
        ["Sharper photos\nread bigger", "Cleaning spacing measured\non a sample against itself", "Measure the spacing\non the whole cloud", "Full-res photos no longer\ncleaned coarser"],
        ["A band vanished,\nsliver volumes", "Colour-fitted plane gated out,\nnothing to fall back on", "Keep Stage 0's projected\nplane as a backup", "0_left 10 cm³ → −1.5%\n2_left +222% → +37%"],
        ["Leg 9% too big\nagainst the cube", "Stage 0's crop moves the\noptical centre 19–74 px", "Pad the whole photo;\ndo not crop", "Mean error 29.0% → 5.7%\n(6 captures)"],
        ["Two scales\ndisagree", "Marker corners unreliable\non busy texture", "Trust the cube volume;\ncheck removed", "Ruler agrees with\nthe cube scale"],
        ["Reflective floor:\na 15 L 'can'", "Floor fit fails on\nthe mirror sheen", "Shoot on the matte tile\n(capture rule)", "5_right, fanta_red\nexcluded"],
    ]
    draw_table(figure, (0.05, 0.1, 0.90, 0.7), header, rows, [0.2, 0.28, 0.25, 0.27], font_size=11)
    footer(figure, "docs/experiments/2026-09_test_captures/EXPERIMENT_LOG.md")
    pdf.savefig(figure)
    plt.close(figure)


def slide_ruled_out(pdf):
    """Hypotheses tested and ruled out before the crop was found."""
    figure = new_slide("What we ruled out on the way", "Each was tested with a measurement, not argued")
    header = ["Suspect", "Test", "Verdict"]
    rows = [
        ["Cube size / scale", "Cube 10.0 cm, markers 5.0 cm, measured; scale checked against markers", "Not the cause"],
        ["Camera lens (FOV)", "VGGT focal vs iPhone EXIF; worst on the can, which reads right", "Not the cause"],
        ["Photo resolution", "HEIC originals; VGGT at 1022 px", "Worse, or breaks"],
        ["The model itself", "MapAnything, MoGe-2, Meshy AI on the same photos", "Same bias, or unusable"],
        ["How points are merged", "TSDF fusion; inner ghost sheet; silhouette carving", "Cleaner cube, same leg"],
        ["Leg shake, hair, cut position", "Four capture styles; hairless leg; band colour vs plane", "Not the cause"],
        ["Stage 0 off-centre crop", "VGGT on original photos, padded or centre-cropped", "The cause: about half the error"],
    ]
    draw_table(figure, (0.05, 0.14, 0.90, 0.64), header, rows, [0.21, 0.5, 0.29], highlight_rows=(6,), font_size=12)
    footer(figure, "docs/experiments/2026-09_test_captures/; fork docs/experiments/model_swap/")
    pdf.savefig(figure)
    plt.close(figure)


BETWEEN_BANDS = [
    # capture, truth, truth kind, v3 volume, v4 mid volume, v4 final volume
    ("test6", 1398.6, "tape", 1939.4, 1704.0, 1500.5),
    ("test5", 2070.0, "water", 2585.3, 2438.6, 2167.5),
    ("0_right", 1830.0, "water", 2485.2, 2503.9, 1730.8),
    ("1_left", 1600.0, "water", 2125.8, 2154.7, 1599.4),
    ("6_left", 2800.0, "water", 3489.7, 3507.7, 2646.8),
    ("2_left", 1050.0, "water", 3381.0, 1442.0, 1168.1),
]


def percent_error(volume, truth):
    """Signed error in percent."""
    return 100.0 * (volume / truth - 1.0)


def slide_results_chart(pdf):
    """Grouped horizontal bars: error per capture for the three measured versions."""
    figure = new_slide("Volume between the bands: error against ground truth",
                       "Full pipeline, end to end. Bars left of zero read low, right of zero read high.")
    axes = figure.add_axes([0.16, 0.13, 0.6, 0.62])
    series = [("v3", 3, "v3  cut at Stage 5"), ("v4 mid", 4, "v4 midweek  (still cropped)"),
              ("v4 final", 5, "v4 today  (padded photos)")]
    bar_height = 0.25
    clip_at = 45.0
    for series_index, (key, column, label) in enumerate(series):
        for capture_index, row in enumerate(BETWEEN_BANDS):
            error = percent_error(row[column], row[1])
            shown = max(min(error, clip_at), -clip_at)
            y_position = capture_index + (series_index - 1) * (bar_height + 0.03)
            axes.barh(y_position, shown, height=bar_height, color=VERSION_COLOURS[key],
                      label=label if capture_index == 0 else None)
            if key == "v4 final":
                axes.text(shown + (1.0 if shown >= 0 else -1.0), y_position, f"{error:+.1f}%",
                          va="center", ha="left" if shown >= 0 else "right", fontsize=11, color=INK, weight="bold")
            if error > clip_at:
                axes.text(clip_at - 0.8, y_position, f"{error:+.0f}% (band lost)", va="center", ha="right",
                          fontsize=9.5, color=INK)
    axes.axvline(0, color=INK, lw=1.2)
    axes.set_yticks(range(len(BETWEEN_BANDS)))
    axes.set_yticklabels([f"{row[0]}  ({row[2]})" for row in BETWEEN_BANDS], fontsize=12, color=INK)
    axes.invert_yaxis()
    axes.set_xlim(-12, clip_at)
    axes.set_xlabel("volume error, %", fontsize=12, color=INK_SECONDARY)
    axes.grid(axis="x", color=RULE, lw=0.8)
    axes.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axes.spines[side].set_visible(False)
    axes.spines["bottom"].set_color(RULE)
    axes.tick_params(colors=INK_SECONDARY, length=0)
    axes.legend(loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=3, frameon=False, fontsize=11,
                handlelength=1.2, columnspacing=1.6)
    figure.text(0.80, 0.52, "Mean |error|", fontsize=13, weight="bold", color=INK)
    figure.text(0.80, 0.465, "v3 (sound runs)   31.4%", fontsize=12, color=INK_SECONDARY)
    figure.text(0.80, 0.42, "v4 midweek         29.0%", fontsize=12, color=INK_SECONDARY)
    figure.text(0.80, 0.375, "v4 today              5.7%", fontsize=12, color=INK, weight="bold")
    figure.text(0.80, 0.30, "Mean bias", fontsize=13, weight="bold", color=INK)
    figure.text(0.80, 0.255, "v4 midweek        +29.0%", fontsize=12, color=INK_SECONDARY)
    figure.text(0.80, 0.21, "v4 today              +2.0%", fontsize=12, color=INK, weight="bold")
    footer(figure, "run logs in ~/MU/senior_compare_artifacts; PAD_NOT_CROP.md")
    pdf.savefig(figure)
    plt.close(figure)


def slide_results_table(pdf):
    """Every number behind the chart, plus band girths for the final version."""
    figure = new_slide("Full results table: volume between the bands (cm³)",
                       "Truth: tape disc model (test6) or water displacement (others)")
    header = ["Capture", "Truth", "v3  (cut at Stage 5)", "v4 midweek", "v4 today (padded)"]
    rows = []
    for capture, truth, kind, version_three, version_mid, version_final in BETWEEN_BANDS:
        note = "  band lost" if capture == "2_left" else ""
        rows.append([capture, f"{truth:.0f} ({kind})",
                     f"{version_three:.0f}   {percent_error(version_three, truth):+.1f}%{note}",
                     f"{version_mid:.0f}   {percent_error(version_mid, truth):+.1f}%",
                     f"{version_final:.0f}   {percent_error(version_final, truth):+.1f}%"])
    rows.append(["Mean |error|", "", "63.2%  (31.4% without 2_left)", "29.0%", "5.7%"])
    rows.append(["Mean bias", "", "+63.2%", "+29.0%", "+2.0%"])
    draw_table(figure, (0.05, 0.14, 0.90, 0.64), header, rows, [0.14, 0.17, 0.26, 0.2, 0.23],
               highlight_rows=(6, 7), bold_columns=(4,), font_size=12)
    footer(figure, "v3: 4 Sep cohort + 18 Sep test runs; v4 midweek: 19 Sep; v4 today: 21 Sep")
    pdf.savefig(figure)
    plt.close(figure)


def slide_girths(pdf):
    """Band girths against the tape, v4 midweek vs today."""
    figure = new_slide("Band circumference against the tape (cm)", "Lower band / upper band, measured at the cut planes")
    header = ["Capture", "Tape lower / upper", "v4 midweek (cropped)", "v4 today (padded)"]
    rows = [
        ["test6", "19.0 / 28.0", "19.95 (+5%) / 31.85 (+14%)", "19.61 (+3%) / 29.42 (+5%)"],
        ["test5", "22.0 / 32.5", "22.16 (+1%) / 34.55 (+6%)", "22.19 (+1%) / 32.86 (+1%)"],
        ["0_right", "20.5 / 29.5", "19.98 (−3%) / 33.30 (+13%)", "18.59 (−9%) / 29.45 (0%)"],
        ["1_left", "21.5 / 32.0", "20.80 (−3%) / 33.95 (+6%)", "19.89 (−7%) / 30.13 (−6%)"],
        ["6_left", "24.3 / 35.0", "23.69 (−3%) / 39.10 (+12%)", "22.15 (−9%) / 34.99 (0%)"],
        ["2_left", "18.5 / 27.5", "19.05 (+3%) / 30.61 (+11%)", "18.69 (+1%) / 27.52 (0%)"],
    ]
    draw_table(figure, (0.05, 0.2, 0.90, 0.58), header, rows, [0.15, 0.2, 0.33, 0.32], bold_columns=(3,), font_size=12.5)
    figure.text(0.05, 0.12, "The upper band is now within 1% on four of six captures. The lower band reads a few percent low",
                fontsize=12, color=INK_SECONDARY)
    figure.text(0.05, 0.085, "on the cohort; tape repeatability measured on test5 was 0.8 cm on average (about 4%).",
                fontsize=12, color=INK_SECONDARY)
    footer(figure, "Stage 6 circumference output in each run log")
    pdf.savefig(figure)
    plt.close(figure)


TEST6_PROFILE = [
    # height above lower band (cm), tape, v4 midweek (cropped), v4 today (padded) — same measurement method
    (0, 19.0, 19.85, 19.77), (2, 19.0, 19.86, 19.62), (4, 19.2, 20.85, 20.60), (6, 20.2, 22.00, 21.76),
    (8, 21.4, 23.28, 22.97), (10, 23.0, 24.71, 24.38), (12, 24.9, 26.27, 25.86), (14, 26.4, 27.76, 27.33),
    (16, 27.9, 29.28, 28.64), (18, 29.1, 30.39, 29.62), (20, 29.5, 31.16, 30.15), (22, 29.4, 31.27, 29.97),
    (24, 28.8, 30.93, 29.26), (26, 28.0, 30.50, 28.71), (28, 28.0, 30.44, 29.64),
]


RING_RUNS = [
    ("v3", "output_test6", "v3  reworked\n4x MLS, alpha wrap"),
    ("v4 mid", "output_test6_mls16", "v4  after stacked MLS\n4x + 16x, Poisson"),
    ("v4 final", "output_test6_pad", "v4  final\nstacked MLS + pad"),
]
RING_FRACTIONS = [0.1, 0.5, 0.9]
RING_MESH_COLOUR = "#b3261e"
RING_POINT_COLOUR = "#2f3a44"
RING_TAPE_COLOUR = "#a3a19b"
RING_HALF_WIDTH_CM = 6.5
TEST6_RULER_CM = 27.5


def load_ring_run(run_name):
    """One test6 run from disk: cleaned leg cloud, uncut solid, cube scale, band heights, volume."""
    import csv
    import json

    import numpy
    import open3d
    import trimesh

    debug = PROJECT_ROOT / run_name / "for_debug"
    cloud = numpy.asarray(open3d.io.read_point_cloud(str(debug / "03_clean/objects/leg.ply")).points)
    solid = trimesh.load(str(debug / "05_watertight/mesh/leg_no_cut.ply"), process=False)
    box = trimesh.load(str(debug / "05_watertight/mesh/box.ply"), process=False)
    scale_cm = (1000.0 / abs(box.volume)) ** (1.0 / 3.0)
    planes_file = json.load(open(debug / "03_clean/debug/cutting_line_levelled.json"))
    band_heights = sorted(plane["centroid"][2] for plane in planes_file["markers"])
    volume_cm3 = float("nan")
    method = "?"
    with open(debug / "06_volume/volumes.csv") as handle:
        for row in csv.DictReader(handle):
            if row["name"].startswith("leg_cut"):
                volume_cm3 = float(row["real_vol_cm3"])
                method = row["method"]
    return {"cloud": cloud, "solid": solid, "scale_cm": scale_cm, "lower": band_heights[0],
            "upper": band_heights[-1], "volume_cm3": volume_cm3, "method": method}


def tape_girth_at(fraction):
    """The tape circumference at this fraction of the way from the lower band to the upper one."""
    import csv

    import numpy

    heights = []
    girths = []
    with open(TAPE_PROFILE_PATH) as handle:
        for row in csv.DictReader(handle):
            heights.append(float(row["height_cm"]))
            girths.append(float(row["circumference_cm"]))
    return float(numpy.interp(fraction * TEST6_RULER_CM, heights, girths))


def draw_ring(axes, run, fraction, tape_girth):
    """One slice: cleaned points in grey, the solid's outline in red, the tape as a dashed circle."""
    import math

    import numpy
    from ring_gallery import fit_ring, mesh_section, polygon_area, slice_points

    height = run["lower"] + fraction * (run["upper"] - run["lower"])
    in_plane = slice_points(run["cloud"], height, run["scale_cm"])
    centre, _, _, _, _ = fit_ring(in_plane)
    centred_points = in_plane - centre
    axes.scatter(centred_points[:, 0], centred_points[:, 1], s=3.5, color=RING_POINT_COLOUR, lw=0, zorder=3)

    mesh_girth = 0.0
    for loop in mesh_section(run["solid"], height, run["scale_cm"], numpy.zeros(2)):
        centred_loop = loop - centre
        closed_loop = numpy.vstack([centred_loop, centred_loop[:1]])
        axes.plot(closed_loop[:, 0], closed_loop[:, 1], color=RING_MESH_COLOUR, linewidth=1.6, zorder=2)
        segment_lengths = numpy.linalg.norm(numpy.diff(closed_loop, axis=0), axis=1)
        if polygon_area(centred_loop) > 1.0:
            mesh_girth += float(segment_lengths.sum())

    tape_radius = tape_girth / (2 * math.pi)
    angles = numpy.linspace(0, 2 * math.pi, 200)
    axes.plot(tape_radius * numpy.cos(angles), tape_radius * numpy.sin(angles),
              color=RING_TAPE_COLOUR, linewidth=1.2, linestyle=(0, (3, 2)), zorder=1)

    axes.set_xlim(-RING_HALF_WIDTH_CM, RING_HALF_WIDTH_CM)
    axes.set_ylim(-RING_HALF_WIDTH_CM, RING_HALF_WIDTH_CM)
    axes.set_aspect("equal")
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_color(RULE)
    girth_error = 100 * (mesh_girth / tape_girth - 1)
    axes.text(0.5, -0.03, f"outline {mesh_girth:.1f} cm   {girth_error:+.0f}%", transform=axes.transAxes,
              ha="center", va="top", fontsize=10, color=INK)


def slide_rings(pdf):
    """test6 sliced low, middle and high: v3, v4 after the stacked MLS, and v4 final."""
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "docs/experiments/2026-09_test_captures"))

    figure = new_slide("Ring gallery: test6 cross-sections",
                       "Dark dots = cleaned points (on top),  red = mesh outline,  grey dashed = tape;  every panel is the same 13 cm window")
    runs = [load_ring_run(run_name) for _, run_name, _ in RING_RUNS]
    column_left = 0.2
    column_width = 0.24
    row_top = 0.705
    row_height = 0.165
    for column_index, (version, _, label) in enumerate(RING_RUNS):
        run = runs[column_index]
        centre_x = column_left + column_index * column_width + column_width / 2
        title, detail = label.split("\n")
        volume_error = 100 * (run["volume_cm3"] / TEST6_TAPE_VOLUME_CM3 - 1)
        figure.text(centre_x, 0.785, title, fontsize=13, weight="bold", ha="center", va="bottom", color=INK)
        figure.text(centre_x, 0.755, detail, fontsize=11, ha="center", va="bottom", color=INK_SECONDARY)
        figure.text(centre_x, 0.722, f"{run['volume_cm3']:.0f} cm³  ({volume_error:+.1f}%)", fontsize=12,
                    ha="center", va="bottom", color=INK, weight="bold" if version == "v4 final" else "normal")
    figure.text(0.05, 0.722, "volume (tape 1398.6 cm³)", fontsize=11, color=INK_SECONDARY, va="bottom")
    for row_index, fraction in enumerate(RING_FRACTIONS):
        tape_girth = tape_girth_at(fraction)
        bottom = row_top - (row_index + 1) * row_height - row_index * 0.04
        position_name = ("near lower band", "middle", "near upper band")[row_index]
        figure.text(0.05, bottom + row_height / 2, f"{position_name}\n{fraction:.0%} of the way\ntape {tape_girth:.1f} cm",
                    fontsize=11, color=INK_SECONDARY, va="center", linespacing=1.4)
        for column_index, run in enumerate(runs):
            axes = figure.add_axes([column_left + column_index * column_width + (column_width - row_height * 0.5625) / 2,
                                    bottom, row_height * 0.5625, row_height])
            draw_ring(axes, run, fraction, tape_girth)
    footer(figure, "output_test6, output_test6_mls16, output_test6_pad; mesh = leg_no_cut.ply")
    pdf.savefig(figure)
    plt.close(figure)


SKELETON_GALLERY = pathlib.Path(__file__).resolve().parent / "2026-09-21_ring_gallery_skeleton.png"


def slide_skeleton_rings(pdf):
    """test6 rings without and with the limb skeleton step (image drawn by the experiment script)."""
    figure = new_slide("Limb skeleton: smoothing each ring",
                       "Each slice fitted with one smooth curve; outer spurs moved in, dents moved out, gaps filled on the curve")
    image = plt.imread(str(SKELETON_GALLERY))
    axes = figure.add_axes([0.05, 0.08, 0.90, 0.74])
    axes.imshow(image)
    axes.axis("off")
    footer(figure, "work/test6_skel_off, work/test6_skel_on; pipeline/core/limb_skeleton.py (LIMB_SKELETON=on)")
    pdf.savefig(figure)
    plt.close(figure)


def slide_skeleton_volumes(pdf):
    """Volume with the limb skeleton step off and on, all six captures."""
    figure = new_slide("Limb skeleton: effect on volume",
                       "Stages 3–6 rerun on the padded runs, step off and on; volume between the bands")
    header = ["Capture", "Truth (cm³)", "Skeleton off", "Skeleton on"]
    rows = [
        ["test6", "1398.6 tape", "1490.4   +6.6%", "1485.2   +6.2%"],
        ["test5", "2070 water", "2165.8   +4.6%", "2167.6   +4.7%"],
        ["0_right", "1830 water", "1734.5   −5.2%", "1743.5   −4.7%"],
        ["1_left", "1600 water", "1612.0   +0.8%", "1591.1   −0.6%"],
        ["6_left", "2800 water", "2648.8   −5.4%", "2647.2   −5.5%"],
        ["2_left", "1050 water", "1179.4   +12.3%", "1180.2   +12.4%"],
        ["Mean |error|", "", "5.8%", "5.7%"],
        ["Mean error (bias)", "", "+2.3%", "+2.1%"],
    ]
    draw_table(figure, (0.05, 0.2, 0.90, 0.62), header, rows, [0.25, 0.25, 0.25, 0.25],
               highlight_rows=(6, 7), font_size=12)
    figure.text(0.05, 0.12, "Shape is cleaner (test6 upper rings: outline error +3–5% → +1–2%); volume barely moves.",
                fontsize=12.5, color=INK)
    figure.text(0.05, 0.08, "Nothing got worse, so the step is now on by default (LIMB_SKELETON=on).",
                fontsize=12.5, color=INK_SECONDARY)
    footer(figure, "work/<capture>_skel_off, work/<capture>_skel_on, 21 Sep")
    pdf.savefig(figure)
    plt.close(figure)


def slide_profile(pdf):
    """test6 girth every 2 cm: tape vs cropped vs padded."""
    figure = new_slide("test6: circumference every 2 cm along the leg", "Tape measured every 2 cm; the pipeline sliced at the same heights")
    axes = figure.add_axes([0.08, 0.14, 0.62, 0.66])
    heights = [row[0] for row in TEST6_PROFILE]
    axes.plot(heights, [row[1] for row in TEST6_PROFILE], color=TAPE_COLOUR, lw=2.2, marker="o", ms=5, label="tape (truth)")
    axes.plot(heights, [row[2] for row in TEST6_PROFILE], color=VERSION_COLOURS["v4 mid"], lw=2, marker="o", ms=5,
              label="v4 midweek (cropped)")
    axes.plot(heights, [row[3] for row in TEST6_PROFILE], color=VERSION_COLOURS["v4 final"], lw=2, marker="o", ms=5,
              label="v4 today (padded)")
    axes.set_xlabel("height above the lower band, cm", fontsize=12, color=INK_SECONDARY)
    axes.set_ylabel("circumference, cm", fontsize=12, color=INK_SECONDARY)
    axes.grid(color=RULE, lw=0.8)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(RULE)
    axes.tick_params(colors=INK_SECONDARY, length=0)
    axes.legend(loc="lower right", frameon=False, fontsize=11)
    header = ["test6", "Truth", "Midweek", "Today"]
    rows = [["Length, cm", "27.5", "29.92\n+8.8%", "28.87\n+5.0%"],
            ["Girth, mean", "tape", "+5.2%", "+1.7%"],
            ["Volume", "1398.6", "+21.8%", "+7.3%"]]
    draw_table(figure, (0.72, 0.5, 0.26, 0.28), header, rows, [0.27, 0.19, 0.29, 0.25], font_size=9.5, bold_columns=(3,))
    figure.text(0.73, 0.43, "What remains on test6 is mostly", fontsize=12, color=INK)
    figure.text(0.73, 0.395, "length (band separation +5%).", fontsize=12, color=INK)
    figure.text(0.73, 0.34, "Open question: was the ruler read", fontsize=12, color=INK_SECONDARY)
    figure.text(0.73, 0.305, "cord centre to centre, or between", fontsize=12, color=INK_SECONDARY)
    figure.text(0.73, 0.27, "inner edges? One cord ≈ 3.6%.", fontsize=12, color=INK_SECONDARY)
    footer(figure, "docs/experiments/2026-09_test_captures/test6_tape_profile.csv; fork CROP_TEST.md")
    pdf.savefig(figure)
    plt.close(figure)


def slide_older_versions(pdf):
    """The comparisons that exist for v1 and v2, on their own quantities."""
    figure = new_slide("v1 and v2: the numbers that exist", "They measured different quantities, so they are not in the main table")
    header = ["Comparison", "Quantity", "Captures", "v1 Old", "v2 / v3 Reworked"]
    rows = [
        ["README set", "below one band", "5 older captures", "22.17%", "3.29%  (re-run 3.12%)"],
        ["Cohort, 4 Sep", "foot to upper band", "0_left, 0_right, 1_left, 1_right", "11.8%", "34.4%  (v3)"],
        ["test5, 18 Sep", "old cut: 3 markers, 40.8 cm", "test5", "not comparable", "—"],
    ]
    draw_table(figure, (0.05, 0.46, 0.90, 0.32), header, rows, [0.16, 0.23, 0.27, 0.14, 0.2], font_size=12)
    bullet_list(figure, 0.05, 0.38, [
        "v1 cannot cut between two bands; it only measures below one",
        "On the cohort, v1's 11.8% came mostly from leaky voxel flood-fill meshes (3 of 4 runs)",
        "The Stage 0 crop, fixed today, is the largest known reason v3 trailed v1 on the cohort",
        "v4 has not yet been re-run on the README set or in below-one-band mode",
    ], font_size=13, spacing=0.058)
    footer(figure, "README.md; 4 Sep old-vs-new comparison (session log)")
    pdf.savefig(figure)
    plt.close(figure)


def slide_next(pdf):
    """Open items."""
    figure = new_slide("Open items")
    bullet_list(figure, 0.06, 0.78, [
        "Re-run the can control: its cube fell to the alpha fallback on today's run",
        "Ruler definition on test6: cord centre to centre, or inner edges?",
        "Re-run the README set and the below-one-band mode on v4",
        "Remaining cohort captures (0_left, 1_right, 2_right, 3–6) on v4",
        "Capture rules: matte floor, cube and both bands in every photo",
        "Deferred, lower priority now: fine-tuning VGGT; training a MoGe–VGGT join",
    ], font_size=16, spacing=0.085)
    footer(figure)
    pdf.savefig(figure)
    plt.close(figure)


def main():
    """Render every slide into one PDF."""
    with PdfPages(OUTPUT) as pdf:
        slide_title(pdf)
        slide_versions(pdf)
        slide_v3_v4_glance(pdf)
        slide_v3_v4_stages(pdf)
        slide_v3_v4_effects(pdf)
        slide_rings(pdf)
        slide_skeleton_rings(pdf)
        slide_skeleton_volumes(pdf)
        slide_problems(pdf)
        slide_ruled_out(pdf)
        slide_results_chart(pdf)
        slide_results_table(pdf)
        slide_girths(pdf)
        slide_profile(pdf)
        slide_older_versions(pdf)
        slide_next(pdf)
    print(OUTPUT)


if __name__ == "__main__":
    main()
