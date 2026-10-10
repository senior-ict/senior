"""Build the 10 October 2026 deck: what changed in commit 5ab597f and why.

The deck explains two pipeline changes to someone who has not seen the code:

  slides 2-4    the cut moves from the middle of each painted band to the band's
                inner edge, because the bands are stripes about 2 cm wide
  slides 5-8    box mending, explained from scratch: what the reference cube is
                for, the two things wrong with its points, the four steps that
                fix them, and when the step does nothing at all
  slides 9-11   what the two changes measured, the leg-hair finding, and what
                is still open

Every picture is drawn from a real run on disk, not sketched. The box-mending
panels run `pipeline/core/box_mending.py` live on an unmended point cloud, so
what the slides show is what the pipeline does.

    python docs/reports/make_pipeline_change_deck.py

Needs these run directories, which are not committed (outputs never are):
`output_test2_champ` (an unmended cube, the bad capture), `output_test6` (an
unmended cube, a sound capture) and `output_test2_champ_hairless` (a run of the
new pipeline, used for the band-stripe picture).
"""
import json
import pathlib
import sys
import textwrap

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, Rectangle

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.core import band_edges, box_mending  # noqa: E402
from pipeline.core.cube_fit import (  # noqa: E402
    YAW_STEP_DEGREES, fit_cube, guess_cube_at_yaw, mean_squared_distance)

OUTPUT_PDF = HERE / "2026-10-10_pipeline_change_deck.pdf"
SLIDE_PNG_DIRECTORY = HERE / "figures/2026-10-10_deck_slides"

BAD_CAPTURE_RUN = PROJECT_ROOT / "output_test2_champ"
SOUND_CAPTURE_RUN = PROJECT_ROOT / "output_test6"
NEW_PIPELINE_RUN = PROJECT_ROOT / "output_test2_champ_hairless"

SLIDE_SIZE = (13.33, 7.5)
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8882"
SURFACE = "#fcfcfb"
RULE = "#e4e2dc"
HIGHLIGHT = "#eaf2fc"
BEFORE_COLOUR = "#b9b6ae"
AFTER_COLOUR = "#2a78d6"
ADDED_COLOUR = "#c2410c"
BAND_COLOUR = "#2f7d32"
TRUTH_COLOUR = INK
CUBE_VIEW_FACES = (("top", 2, 1), ("x-", 0, -1), ("y-", 1, -1))   # the faces this view lights
FACE_COLOURS = {"x+": "#2a78d6", "x-": "#7fb0e8", "y+": "#1b7f5a", "y-": "#7cc3a5",
                "top": "#b07d2a", "bottom": "#c2410c"}
NEAR_EDGE_MILLIMETRES = 2.0      # a point this close to an edge could go to either face

SLIDE_COUNTER = {"number": 0}


# ---------------------------------------------------------------- slide chrome

def new_slide(title, subtitle=None, subtitle_width=108):
    """A blank 16:9 slide with its title and a subtitle wrapped to fit the page."""
    figure = plt.figure(figsize=SLIDE_SIZE, facecolor=SURFACE)
    figure.text(0.05, 0.945, title, fontsize=23, weight="bold", color=INK, va="top")
    if subtitle:
        wrapped = "\n".join(textwrap.wrap(subtitle, subtitle_width))
        figure.text(0.05, 0.878, wrapped, fontsize=12.5, color=INK_SECONDARY,
                    va="top", linespacing=1.5)
    return figure


def footer(figure, source=None):
    """Stamp the slide number, and where the slide's numbers came from."""
    SLIDE_COUNTER["number"] += 1
    figure.text(0.95, 0.035, str(SLIDE_COUNTER["number"]), fontsize=10,
                color=INK_MUTED, ha="right")
    if source:
        figure.text(0.05, 0.035, f"Source: {source}", fontsize=9, color=INK_MUTED)


def paragraph(figure, left, top, text, width_characters, font_size=11.5, colour=INK,
              weight="normal"):
    """A block of prose wrapped to a character budget and anchored at its top-left.

    Blank lines in `text` are kept, so a paragraph break can be written as a
    double newline.
    """
    wrapped_blocks = []
    for block in text.split("\n\n"):
        wrapped_blocks.append("\n".join(textwrap.wrap(block, width_characters)))
    figure.text(left, top, "\n\n".join(wrapped_blocks), fontsize=font_size,
                color=colour, va="top", linespacing=1.75, weight=weight)


def draw_table(figure, rectangle, header, rows, column_widths, highlight_rows=(),
               font_size=11):
    """A plain table: bold header, thin rules, optional highlighted rows."""
    left, bottom, width, height = rectangle
    axes = figure.add_axes([left, bottom, width, height])
    axes.axis("off")
    row_count = len(rows) + 1
    row_height = 1.0 / row_count
    column_positions = [0.0]
    for column_width in column_widths[:-1]:
        column_positions.append(column_positions[-1] + column_width)

    for row_index in range(row_count):
        row_top = 1.0 - row_index * row_height
        if row_index - 1 in highlight_rows:
            axes.add_patch(Rectangle((0, row_top - row_height), 1, row_height,
                                     color=HIGHLIGHT, lw=0))
        is_header = row_index == 0
        if is_header:
            cells = header
            cell_weight = "bold"
            rule_colour = INK
            rule_width = 1.2
        else:
            cells = rows[row_index - 1]
            cell_weight = "normal"
            rule_colour = RULE
            rule_width = 0.8
        for column_index, cell in enumerate(cells):
            axes.text(column_positions[column_index] + 0.008,
                      row_top - row_height / 2, str(cell), fontsize=font_size,
                      va="center", ha="left", weight=cell_weight, color=INK)
        axes.axhline(row_top - row_height, color=rule_colour, lw=rule_width)
    axes.set_xlim(0, 1)
    axes.set_ylim(0, 1)
    return axes


def bullet_list(figure, left, top, lines, line_gap=0.062, font_size=12.5,
                width_characters=78):
    """Bullets wrapped to a character budget; a line starting with '-' is a sub-point."""
    y_position = top
    for line in lines:
        if line.startswith("-"):
            bullet_text = line[1:].strip()
            marker = "–"
            marker_indent = 0.022
            text_indent = 0.042
            marker_colour = INK_MUTED
            text_colour = INK_SECONDARY
            size = font_size - 1
        else:
            bullet_text = line
            marker = "•"
            marker_indent = 0.0
            text_indent = 0.018
            marker_colour = AFTER_COLOUR
            text_colour = INK
            size = font_size
        wrapped = "\n".join(textwrap.wrap(bullet_text, width_characters))
        figure.text(left + marker_indent, y_position, marker, fontsize=size,
                    color=marker_colour, va="top")
        figure.text(left + text_indent, y_position, wrapped, fontsize=size,
                    color=text_colour, va="top", linespacing=1.6)
        extra_lines = wrapped.count("\n")
        y_position -= line_gap * (1 + 0.62 * extra_lines)


def tidy_axes(axes, title=None):
    """Strip the top and right spines and recede the axis lines, deck house style."""
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)
    axes.spines["left"].set_color(RULE)
    axes.spines["bottom"].set_color(RULE)
    axes.tick_params(colors=INK_SECONDARY, labelsize=10)
    if title:
        axes.set_title(title, fontsize=12, color=INK, loc="left", pad=8)


# ----------------------------------------------------------------- loading data

def load_box_points(run_directory):
    """The reference cube's cleaned points and colours from one run."""
    path = run_directory / "for_debug/03_clean/objects/box.ply"
    cloud = o3d.io.read_point_cloud(str(path))
    return np.asarray(cloud.points), np.asarray(cloud.colors)


def load_leg_points(run_directory):
    """The limb's cleaned points and colours from one run."""
    path = run_directory / "for_debug/03_clean/objects/leg.ply"
    cloud = o3d.io.read_point_cloud(str(path))
    return np.asarray(cloud.points), np.asarray(cloud.colors)


def centimetres_per_unit(box_points):
    """How many centimetres one scene unit is, taken from the fitted cube's side."""
    fit = fit_cube(box_points)
    return box_mending.REFERENCE_SIDE_CM / fit["side"], fit


def measure_band_stripes(run_directory):
    """Where the two painted stripes start and end along the line joining them.

    Returns the band points' positions in centimetres, both stripes' edges, and
    the centre-to-centre and inner-to-inner spans.
    """
    leg_points, leg_colours = load_leg_points(run_directory)
    box_points, _ = load_box_points(run_directory)
    scale, _ = centimetres_per_unit(box_points)

    cutting_line = json.loads(
        (run_directory / "for_debug/03_clean/debug/cutting_line_levelled.json").read_text())
    centre_markers = cutting_line["candidates"]
    lower_centre = np.array(centre_markers[0]["centroid"])
    upper_centre = np.array(centre_markers[-1]["centroid"])
    axis = upper_centre - lower_centre
    centre_span_cm = float(np.linalg.norm(axis)) * scale
    axis = axis / np.linalg.norm(axis)

    along_cm = (leg_points - lower_centre) @ axis * scale
    is_band = band_edges.band_coloured(leg_colours)

    stripes = {}
    for label, centre_cm in (("lower", 0.0), ("upper", centre_span_cm)):
        near_stripe = is_band & (np.abs(along_cm - centre_cm) < band_edges.SEARCH_WINDOW_CM)
        positions = along_cm[near_stripe]
        stripes[label] = {
            "positions": positions,
            "low": float(np.percentile(positions, band_edges.EDGE_PERCENTILE)),
            "high": float(np.percentile(positions, 100 - band_edges.EDGE_PERCENTILE)),
            "centre": centre_cm}

    inner_span_cm = stripes["upper"]["low"] - stripes["lower"]["high"]
    return {"along_cm": along_cm, "is_band": is_band, "stripes": stripes,
            "centre_span_cm": centre_span_cm, "inner_span_cm": inner_span_cm}


def mend_one_box(run_directory):
    """Run the pipeline's own mender on a run's cube points, keeping every stage.

    Returns the raw points, the points after snapping, the points the filler
    added and the mender's report -- all in the cube's own frame and in
    centimetres, so they can be drawn directly.
    """
    raw_points, raw_colours = load_box_points(run_directory)
    scale, fit = centimetres_per_unit(raw_points)
    half_side_cm = box_mending.REFERENCE_SIDE_CM / 2.0

    raw_local_cm = box_mending.to_cube_frame(raw_points, fit) * scale
    tolerance_cm = box_mending.DEFAULT_TOLERANCE_MM / 10.0
    cell_cm = box_mending.DEFAULT_CELL_MM / 10.0
    snapped_local_cm, _ = box_mending.snap_onto_faces(raw_local_cm, half_side_cm,
                                                      tolerance_cm)
    added_local_cm, _ = box_mending.fill_empty_cells(snapped_local_cm, half_side_cm,
                                                     cell_cm)
    _, _, report = box_mending.mend_reference_points(raw_points, raw_colours)

    return {"raw": raw_local_cm, "snapped": snapped_local_cm, "added": added_local_cm,
            "half_side_cm": half_side_cm, "cell_cm": cell_cm, "report": report,
            "raw_count": len(raw_points), "scene_points": raw_points,
            "yaw_degrees": fit["yaw_degrees"]}


def face_cell_occupancy(capture, face_axis, face_side):
    """Which cells of one cube face held a point before the filler ran.

    `face_axis` is 0, 1 or 2 and `face_side` is +1 or -1, the same way
    box_mending names a face. Returns the cell edges in centimetres and a
    square boolean grid, laid out exactly as box_mending.fill_empty_cells
    lays it out so the counts match the pipeline's own report.
    """
    half_side_cm = capture["half_side_cm"]
    cell_cm = capture["cell_cm"]
    snapped = capture["snapped"]
    axis, side = box_mending.nearest_face(snapped)
    on_face = (axis == face_axis) & (side == face_side)

    other_axes = []
    for candidate_axis in (0, 1, 2):
        if candidate_axis != face_axis:
            other_axes.append(candidate_axis)

    steps = max(2, int(np.ceil(2 * half_side_cm / cell_cm)))
    edges = np.linspace(-half_side_cm, half_side_cm, steps + 1)
    occupied = np.zeros((steps, steps), dtype=bool)
    if on_face.any():
        first = np.clip(np.digitize(snapped[on_face, other_axes[0]], edges) - 1,
                        0, steps - 1)
        second = np.clip(np.digitize(snapped[on_face, other_axes[1]], edges) - 1,
                         0, steps - 1)
        occupied[first, second] = True
    return edges, occupied


def face_assignment(capture):
    """How the mender assigns each point to a face, and how clear-cut that was.

    Returns the yaw sweep the fit runs, the face each point was given, and the
    gap in millimetres between a point's largest coordinate and its
    second-largest -- the margin by which its face won.
    """
    local_points_cm = capture["raw"]
    axis_index, side_sign = box_mending.nearest_face(local_points_cm)

    magnitudes = np.abs(local_points_cm)
    ordered = np.sort(magnitudes, axis=1)
    margin_millimetres = (ordered[:, 2] - ordered[:, 1]) * 10.0

    yaw_degrees = np.arange(0.0, 90.0, YAW_STEP_DEGREES)
    costs = []
    for one_yaw_degrees in yaw_degrees:
        yaw = np.radians(one_yaw_degrees)
        centre_x, centre_y, bottom, side = guess_cube_at_yaw(capture["scene_points"], yaw)
        costs.append(mean_squared_distance(capture["scene_points"], yaw, centre_x,
                                           centre_y, bottom, side))
    return {"axis_index": axis_index, "side_sign": side_sign,
            "margin_millimetres": margin_millimetres,
            "yaw_degrees": yaw_degrees, "costs": np.array(costs),
            "best_yaw_degrees": capture["yaw_degrees"]}


def isometric(corner_x, corner_y, corner_z):
    """Project a point of the cube onto the page, seen from a corner above it."""
    horizontal = (corner_x - corner_y) * np.cos(np.radians(30))
    vertical = (corner_x + corner_y) * np.sin(np.radians(30)) + corner_z
    return horizontal, vertical


def offsets_from_faces(local_points_cm, half_side_cm):
    """Signed distance in millimetres from each point to its nearest cube face."""
    axis, _ = box_mending.nearest_face(local_points_cm)
    rows = np.arange(len(local_points_cm))
    offsets_cm = np.abs(local_points_cm[rows, axis]) - half_side_cm
    return offsets_cm * 10.0


# --------------------------------------------------------------------- slide 1

def slide_title(pdf):
    """Cover slide: the headline result of the commit."""
    figure = plt.figure(figsize=SLIDE_SIZE, facecolor=SURFACE)
    figure.text(0.05, 0.70, "Two changes to the pipeline", fontsize=40, weight="bold",
                color=INK)
    figure.text(0.05, 0.60, "Cut at the bands' inner edges  ·  mend the reference cube",
                fontsize=19, color=INK_SECONDARY)
    figure.add_artist(plt.Line2D([0.05, 0.42], [0.555, 0.555], color=AFTER_COLOUR, lw=3))
    figure.text(0.05, 0.44,
                "Five captures whose ground truth and whose cameras see the same\n"
                "surface now read within 1% on average.",
                fontsize=15, color=INK, va="top", linespacing=1.7)
    figure.text(0.05, 0.16, "commit 5ab597f  ·  keng-branch  ·  10 October 2026",
                fontsize=11.5, color=INK_MUTED)
    pdf.savefig(figure)
    save_slide_png(figure, "01_title")
    plt.close(figure)
    SLIDE_COUNTER["number"] += 1


# --------------------------------------------------------------------- slide 2

def slide_what_changed(pdf):
    """The diff in words: two new modules, four switches, nothing else moved."""
    figure = new_slide("What changed since the previous commit",
                       "cec1b81 → 5ab597f.  134 files and +1996 / −20 lines, but only "
                       "eight of them are pipeline code.")
    bullet_list(figure, 0.05, 0.79, [
        "Two new modules, each one step inside Stage 3:",
        "-pipeline/core/band_edges.py — moves the two cutting planes to the "
        "bands' inner edges",
        "-pipeline/core/box_mending.py — makes the reference cube's points "
        "describe a cube",
        "Four switches in pipeline/config.py, both steps on by default:",
        "-BAND_CUT_EDGE = inner | centre,   BOX_MENDING = on | off,   "
        "BOX_MEND_TOLERANCE_MM = 1.0,   BOX_MEND_CELL_MM = 4.0",
        "Everything else in the commit is measurement, not pipeline:",
        "-five tape profiles, the run-versus-tape scripts, 19 figures, "
        "EXPERIMENT_LOG sections 18-20, and the inputs/test1..test6 rename",
    ], line_gap=0.063, font_size=12.5, width_characters=120)

    draw_table(figure, (0.05, 0.10, 0.9, 0.19),
               ["file", "lines", "what it does"],
               [["pipeline/core/box_mending.py", "+171",
                 "flatten the cube's fuzz, fill its gaps"],
                ["pipeline/core/band_edges.py", "+107",
                 "slide each cutting plane to its stripe's inner edge"],
                ["pipeline/stages/clean.py", "+40 / −2",
                 "calls both, in that order, late in Stage 3"],
                ["pipeline/config.py", "+39 / −6",
                 "the four switches, with the measured effect in comments"]],
               [0.30, 0.10, 0.60], font_size=10.5)
    footer(figure, "git diff --stat cec1b81 5ab597f")
    pdf.savefig(figure)
    save_slide_png(figure, "02_what_changed")
    plt.close(figure)


# --------------------------------------------------------------------- slide 3

def slide_band_is_a_stripe(pdf, stripe_data):
    """The first problem, drawn from a real cloud: the band is 2 cm wide."""
    figure = new_slide("Problem 1: the band is a stripe, not a line",
                       "Every volume is measured between two painted bands. A plane "
                       "fitted to a whole stripe lands in its middle — but the tape is "
                       "read between the facing edges.")

    along_cm = stripe_data["along_cm"]
    is_band = stripe_data["is_band"]
    lower = stripe_data["stripes"]["lower"]
    upper = stripe_data["stripes"]["upper"]

    axes_full = figure.add_axes([0.06, 0.45, 0.56, 0.31])
    axes_full.hist(along_cm[~is_band], bins=90, color="#ddd9d0",
                   label="limb points (not band-coloured)")
    axes_full.hist(along_cm[is_band], bins=60, color=BAND_COLOUR,
                   label="band-coloured points")
    for stripe in (lower, upper):
        axes_full.axvline(stripe["centre"], color=INK_MUTED, lw=1.8, ls="--")
    axes_full.axvline(lower["high"], color=AFTER_COLOUR, lw=2.2)
    axes_full.axvline(upper["low"], color=AFTER_COLOUR, lw=2.2)
    tidy_axes(axes_full, "test2_champ_hairless · all limb points, projected onto the "
                         "line joining the two bands")
    axes_full.set_ylabel("points", fontsize=10.5, color=INK_SECONDARY)
    axes_full.legend(fontsize=9.5, frameon=False, loc="upper left")

    axes_zoom = figure.add_axes([0.06, 0.14, 0.56, 0.19])
    in_window = np.abs(along_cm - upper["centre"]) < 4.0
    axes_zoom.hist(along_cm[in_window & ~is_band], bins=50, color="#ddd9d0")
    axes_zoom.hist(along_cm[in_window & is_band], bins=40, color=BAND_COLOUR)
    axes_zoom.axvspan(upper["low"], upper["high"], color=BAND_COLOUR, alpha=0.10, lw=0)
    axes_zoom.axvline(upper["centre"], color=INK_MUTED, lw=2.0, ls="--",
                      label="plane fitted to the whole stripe (its centre)")
    axes_zoom.axvline(upper["low"], color=AFTER_COLOUR, lw=2.4,
                      label="the stripe's inner edge — where the cut now lands")
    axes_zoom.annotate("", xy=(upper["low"], axes_zoom.get_ylim()[1] * 0.50),
                       xytext=(upper["centre"], axes_zoom.get_ylim()[1] * 0.50),
                       arrowprops=dict(arrowstyle="<|-|>", color=ADDED_COLOUR, lw=1.6))
    axes_zoom.text((upper["low"] + upper["centre"]) / 2,
                   axes_zoom.get_ylim()[1] * 0.56,
                   f"{upper['centre'] - upper['low']:.2f} cm", ha="center", fontsize=10.5,
                   color=ADDED_COLOUR, weight="bold")
    tidy_axes(axes_zoom, "the upper stripe close up")
    axes_zoom.set_xlabel("distance along the limb axis (cm)", fontsize=10.5,
                         color=INK_SECONDARY)
    axes_zoom.legend(fontsize=9.5, frameon=False, loc="upper right")

    figure.text(0.67, 0.76, "Measured on this capture", fontsize=13, weight="bold",
                color=INK, va="top")
    bullet_list(figure, 0.67, 0.70, [
        f"lower stripe {lower['high'] - lower['low']:.2f} cm wide",
        f"upper stripe {upper['high'] - upper['low']:.2f} cm wide",
        f"centre to centre {stripe_data['centre_span_cm']:.2f} cm",
        f"inner to inner {stripe_data['inner_span_cm']:.2f} cm",
        "the tape said 27.0 cm",
    ], line_gap=0.055, font_size=12.5, width_characters=30)

    paragraph(figure, 0.67, 0.36,
              "Across every capture the two choices differ by 2.0–2.5 cm of limb — "
              "about 8% of the length, and the single biggest free choice anywhere "
              "in the pipeline.\n\n"
              "Sliding both planes all the way from the inner edges to the outer "
              "edges swings the reported volume by 15–35%.",
              width_characters=40, font_size=11.5, colour=INK_SECONDARY)
    footer(figure, "output_test2_champ_hairless Stage 3 clouds, read with band_edges.py")
    pdf.savefig(figure)
    save_slide_png(figure, "03_band_is_a_stripe")
    plt.close(figure)


# --------------------------------------------------------------------- slide 4

def slide_inner_edge_fix(pdf, span_rows):
    """How the first change was made, and what it did to the spans."""
    figure = new_slide("Fix 1: slide each plane to its stripe's inner edge",
                       "The plane keeps the orientation Stage 3 fitted to the band. "
                       "Only its position moves, along the line joining the two bands.")
    bullet_list(figure, 0.05, 0.79, [
        "Pick out the band-coloured points: green above the mean of red and blue.",
        "Project them onto the line joining the two band centres.",
        "Take each stripe's 2nd and 98th percentile as its edges, so colour bleed "
        "at the rim is ignored.",
        "Move the lower plane up to its stripe's top, the upper plane down to its "
        "stripe's bottom.",
        "If either stripe has fewer than 40 points, leave both planes where they were.",
    ], line_gap=0.058, font_size=12.5, width_characters=96)

    figure.text(0.05, 0.50, "What every run now reports", fontsize=13, weight="bold",
                color=INK, va="top")
    draw_table(figure, (0.05, 0.15, 0.52, 0.30),
               ["capture", "centre to centre", "inner to inner", "moved"],
               span_rows, [0.34, 0.24, 0.22, 0.20], font_size=11)

    figure.text(0.62, 0.50, "What it was worth", fontsize=13, weight="bold", color=INK,
                va="top")
    draw_table(figure, (0.62, 0.24, 0.33, 0.21),
               ["capture", "before", "after"],
               [["test1_6", "+6.9%", "+0.2%"],
                ["test2_keng", "+6.9%", "+1.7%"],
                ["test1_5", "+4.8%", "+0.1%"]],
               [0.40, 0.30, 0.30], highlight_rows=(0, 1, 2), font_size=11)
    paragraph(figure, 0.62, 0.20,
              "Volumes with both changes on. The cut is by far the larger of the two "
              "terms; mending moves a sound capture by less than half a percent.",
              width_characters=46, font_size=10.5, colour=INK_MUTED)
    footer(figure, "cutting_line_levelled.json from each run; EXPERIMENT_LOG §20")
    pdf.savefig(figure)
    save_slide_png(figure, "04_inner_edge_fix")
    plt.close(figure)


# --------------------------------------------------------------------- slide 5

def slide_why_the_cube_matters(pdf):
    """Box mending, from scratch: what the cube is and why its shape is the scale."""
    figure = new_slide("Box mending, from the beginning: what the cube is for",
                       "A photograph has no scale. The 10 cm ArUco cube standing in the "
                       "scene is the only thing in it whose size we know.")

    axes = figure.add_axes([0.05, 0.52, 0.90, 0.26])
    axes.axis("off")
    axes.set_xlim(0, 10)
    axes.set_ylim(0, 1.6)
    chain = [("photos", "no units at all"),
             ("3D points", "units of 'whatever'"),
             ("cube mesh", "its volume = 1 unit³"),
             ("the scale", "1 unit³ := 1000 cm³"),
             ("limb volume", "cm³ at last")]
    for index, (heading, caption) in enumerate(chain):
        left = 0.15 + index * 1.95
        is_cube_step = index in (2, 3)
        if is_cube_step:
            edge_colour = AFTER_COLOUR
            face_colour = HIGHLIGHT
            heading_weight = "bold"
        else:
            edge_colour = RULE
            face_colour = "white"
            heading_weight = "normal"
        axes.add_patch(Rectangle((left, 0.35), 1.6, 0.95, lw=1.6,
                                 edgecolor=edge_colour, facecolor=face_colour))
        axes.text(left + 0.8, 0.98, heading, fontsize=13, ha="center", color=INK,
                  weight=heading_weight)
        axes.text(left + 0.8, 0.58, caption, fontsize=10, ha="center",
                  color=INK_SECONDARY)
        if index < len(chain) - 1:
            axes.add_patch(FancyArrowPatch((left + 1.68, 0.82), (left + 1.9, 0.82),
                                           arrowstyle="-|>", mutation_scale=16,
                                           color=INK_MUTED, lw=1.4))

    figure.text(0.05, 0.47,
                "Stage 6 takes the scale from the cube MESH's volume, not from its "
                "points. So whatever the mesher does to the cube\nis divided into every "
                "number we report: a 1% error in the cube's volume is a 1% error in the "
                "limb's.",
                fontsize=13, color=INK, va="top", linespacing=1.7)

    figure.text(0.05, 0.34, "Why the cube may be corrected and the limb may not",
                fontsize=13.5, weight="bold", color=INK, va="top")
    paragraph(figure, 0.05, 0.285,
              "The cube is the one object in the scene whose true shape is known "
              "exactly — six flat faces, all 10 cm, all at right angles. Correcting "
              "its points invents nothing; it only enforces what we already know.\n\n"
              "The limb's true shape is what we are trying to measure. Nothing may be "
              "enforced on it, so none of this is applied there.",
              width_characters=118, font_size=12, colour=INK_SECONDARY)
    footer(figure, "pipeline/stages/volume.py; pipeline/core/box_mending.py docstring")
    pdf.savefig(figure)
    save_slide_png(figure, "05_why_the_cube_matters")
    plt.close(figure)


# --------------------------------------------------------------------- slide 6

def slide_two_defects(pdf, bad_capture):
    """The two things wrong with the cube's points, both from real data."""
    figure = new_slide("What is wrong with the cube's points: fuzz, and gaps",
                       "test2_champ, a capture where the cube happened to be "
                       "photographed nearly corner-on. 5,418 points.")

    offsets_mm = offsets_from_faces(bad_capture["raw"], bad_capture["half_side_cm"])
    axes_left = figure.add_axes([0.07, 0.42, 0.37, 0.34])
    axes_left.hist(offsets_mm, bins=80, range=(-8, 8), color=BEFORE_COLOUR)
    axes_left.axvline(0, color=INK, lw=1.6)
    axes_left.axvspan(-box_mending.DEFAULT_TOLERANCE_MM, box_mending.DEFAULT_TOLERANCE_MM,
                      color=AFTER_COLOUR, alpha=0.20, lw=0,
                      label="within 1 mm — left alone")
    tidy_axes(axes_left, "the fuzz: how far each point sits off its nearest face")
    axes_left.set_xlabel("distance from the face (mm, + is outside)", fontsize=10.5,
                         color=INK_SECONDARY)
    axes_left.set_ylabel("points", fontsize=10.5, color=INK_SECONDARY)
    axes_left.legend(fontsize=10, frameon=False, loc="upper left")
    axes_left.text(0.99, 0.54, f"the points sit {bad_capture['report']['residual_mm']:.2f} mm\n"
                               "off a true cube, and\nscatter on both sides of it",
                   transform=axes_left.transAxes, ha="right", va="top", fontsize=10.5,
                   color=INK_SECONDARY, linespacing=1.7)

    axes_right = figure.add_axes([0.56, 0.42, 0.37, 0.34])
    coverage = bad_capture["report"]["coverage"]
    faces = []
    for face_name, face in coverage.items():
        faces.append((100 * face["covered"] / face["cells"], face_name))
    faces.sort()
    sorted_names = []
    sorted_percent = []
    for percent, face_name in faces:
        sorted_names.append(face_name)
        sorted_percent.append(percent)
    bars = axes_right.barh(sorted_names, sorted_percent, color=BEFORE_COLOUR, height=0.62)
    bars[0].set_color(ADDED_COLOUR)
    for name, percent in zip(sorted_names, sorted_percent):
        axes_right.text(percent + 1.5, name, f"{percent:.0f}%", va="center",
                        fontsize=10.5, color=INK)
    axes_right.set_xlim(0, 112)
    tidy_axes(axes_right, "the gaps: how much of each face has any points on it")
    axes_right.set_xlabel("share of the face's 4 mm cells holding a point (%)",
                          fontsize=10.5, color=INK_SECONDARY)

    paragraph(figure, 0.07, 0.29,
              "The gaps are the expensive one. A face with holes in it cannot be closed "
              "by Poisson reconstruction — the surface tunnels straight through. Stage 4 "
              "detects that (Euler characteristic ≠ 2) and falls back to the alpha-shape "
              "ladder, whose loosest rung wraps the points from outside: on this capture "
              "it floated 2.9 mm clear on every side, 9.1% more volume than the cube its "
              "own points describe.",
              width_characters=128, font_size=12)
    footer(figure, "box_mending.py run on output_test2_champ; Stage 4 log, 2026-10-09")
    pdf.savefig(figure)
    save_slide_png(figure, "06_two_defects")
    plt.close(figure)


# --------------------------------------------------------------------- slide 7

def draw_cross_section(axes, local_points_cm, half_side_cm, slab_half_cm,
                       point_colour, title, show_cube=True):
    """One horizontal slice through the cube seen from above, with the cube's outline."""
    in_slab = np.abs(local_points_cm[:, 2]) < slab_half_cm
    axes.scatter(local_points_cm[in_slab, 0], local_points_cm[in_slab, 1], s=3.0,
                 color=point_colour, lw=0)
    if show_cube:
        axes.add_patch(Rectangle((-half_side_cm, -half_side_cm), 2 * half_side_cm,
                                 2 * half_side_cm, fill=False, lw=1.6, edgecolor=INK))
    axes.set_xlim(-7.2, 7.2)
    axes.set_ylim(-7.2, 7.2)
    axes.set_aspect("equal")
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_color(RULE)
    axes.set_title(title, fontsize=11.5, color=INK, loc="left", pad=6)


def draw_face_from_outside(axes, capture, title):
    """The cube's bottom face seen straight on: the points it has, and the cells filled."""
    half_side_cm = capture["half_side_cm"]
    snapped = capture["snapped"]
    added = capture["added"]
    axis, side = box_mending.nearest_face(snapped)
    on_bottom = (axis == 2) & (side == -1)
    axes.scatter(snapped[on_bottom, 0], snapped[on_bottom, 1], s=2.2,
                 color=AFTER_COLOUR, lw=0, label="points the capture had")
    if len(added):
        added_axis, added_side = box_mending.nearest_face(added)
        added_on_bottom = (added_axis == 2) & (added_side == -1)
        axes.scatter(added[added_on_bottom, 0], added[added_on_bottom, 1], s=7.0,
                     color=ADDED_COLOUR, lw=0, marker="s", label="cells the filler filled")
    axes.add_patch(Rectangle((-half_side_cm, -half_side_cm), 2 * half_side_cm,
                             2 * half_side_cm, fill=False, lw=1.6, edgecolor=INK))
    axes.set_xlim(-7.2, 7.2)
    axes.set_ylim(-7.2, 7.2)
    axes.set_aspect("equal")
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_color(RULE)
    axes.set_title(title, fontsize=11.5, color=INK, loc="left", pad=6)
    axes.legend(fontsize=8.5, frameon=False, loc="lower center", ncol=2,
                bbox_to_anchor=(0.5, -0.10), handletextpad=0.2, columnspacing=1.0)


def slide_the_four_steps(pdf, bad_capture):
    """The mending algorithm itself, four panels, all real points."""
    figure = new_slide("How mending works: four steps, nothing invented",
                       "Panels 1–3 are one horizontal 1 cm slab at the cube's "
                       "mid-height, seen from above; panel 4 looks straight at the "
                       "bottom face. The cube is never chopped into chunks — that is "
                       "only how the picture is drawn.")

    half_side_cm = bad_capture["half_side_cm"]
    panel_bottom = 0.46
    panel_height = 0.31
    panel_width = 0.205
    panel_lefts = [0.055, 0.285, 0.515, 0.745]

    axes_one = figure.add_axes([panel_lefts[0], panel_bottom, panel_width, panel_height])
    draw_cross_section(axes_one, bad_capture["raw"], half_side_cm, 0.5, BEFORE_COLOUR,
                       "1 · the points as they arrive", show_cube=False)

    axes_two = figure.add_axes([panel_lefts[1], panel_bottom, panel_width, panel_height])
    draw_cross_section(axes_two, bad_capture["raw"], half_side_cm, 0.5, BEFORE_COLOUR,
                       "2 · fit an ideal 10 cm cube")

    axes_three = figure.add_axes([panel_lefts[2], panel_bottom, panel_width, panel_height])
    draw_cross_section(axes_three, bad_capture["snapped"], half_side_cm, 0.5,
                       AFTER_COLOUR, "3 · snap the fuzz onto the faces")

    axes_four = figure.add_axes([panel_lefts[3], panel_bottom, panel_width, panel_height])
    draw_face_from_outside(axes_four, bad_capture, "4 · fill every empty cell")

    report = bad_capture["report"]
    captions = [
        "A band of scatter either side of where each face must be, and whole "
        "stretches with nothing on them at all.",
        "Yaw sweep, then Nelder–Mead on five unknowns: yaw, centre x and y, base "
        "height and side. The residual is taken over ALL points, so the fit sits in "
        "the middle of the scatter rather than on its outside.",
        f"Every point more than 1 mm off its nearest face is moved onto it.\n\n"
        f"{report['pulled_in']:,} pulled in, {report['pushed_out']:,} pushed out, "
        f"{report['untouched']:,} already close enough.",
        f"Each face is gridded into 25 × 25 cells of 4 mm, and a point (orange) goes "
        f"into every empty one.\n\n"
        f"{report['added']:,} added here; this face was only 43% covered. "
        f"{bad_capture['raw_count']:,} → {bad_capture['raw_count'] + report['added']:,}.",
    ]
    for left, caption in zip(panel_lefts, captions):
        paragraph(figure, left, 0.395, caption, width_characters=34, font_size=10,
                  colour=INK_SECONDARY)

    paragraph(figure, 0.055, 0.175,
              "Mending does not decide how big the cube is — the fit is driven by the "
              "points, so on this capture 42% of them end up outside the fitted cube "
              "and 58% inside, mean offset +0.10 mm. Where the points say the cube "
              "reconstructed small, mending makes the mesh say so too, instead of "
              "hiding it under a loose wrap.",
              width_characters=140, font_size=11)
    footer(figure, "pipeline/core/box_mending.py run live on output_test2_champ")
    pdf.savefig(figure)
    save_slide_png(figure, "07_four_steps")
    plt.close(figure)


# --------------------------------------------------------------------- slide 8

# Three dots invented for the plain-language slide: one clearly on the right wall,
# one clearly on the top wall, and one in a corner where the rule nearly ties.
PLAIN_EXAMPLE_DOTS = (("A", 4.8, 1.2), ("B", -1.5, 4.9), ("C", 4.6, 4.4))
SIDEWAYS_COLOUR = "#2a78d6"
UP_DOWN_COLOUR = "#b07d2a"


def draw_box_from_above(axes, half_side_cm):
    """The box seen from above as a plain square, with each dot and its two distances."""
    axes.add_patch(Rectangle((-half_side_cm, -half_side_cm), 2 * half_side_cm,
                             2 * half_side_cm, facecolor="#f4f2ec", edgecolor=INK,
                             lw=2.2))
    axes.plot(0, 0, marker="+", markersize=14, color=INK, markeredgewidth=2)
    axes.text(0.25, 0.25, "the middle", fontsize=10, color=INK_SECONDARY)
    axes.text(0, half_side_cm + 0.45, "top wall", fontsize=10, color=INK_SECONDARY,
              ha="center")
    axes.text(half_side_cm + 0.35, -2.2, "right wall", fontsize=10,
              color=INK_SECONDARY, va="center", rotation=-90)

    for name, dot_x, dot_y in PLAIN_EXAMPLE_DOTS:
        axes.plot([0, dot_x], [0, 0], color=SIDEWAYS_COLOUR, lw=2.0, ls=":")
        axes.plot([dot_x, dot_x], [0, dot_y], color=UP_DOWN_COLOUR, lw=2.0, ls=":")
        axes.plot(dot_x, dot_y, marker="o", markersize=9, color=ADDED_COLOUR)
        axes.text(dot_x - 0.8, dot_y + 0.25, name, fontsize=13, weight="bold",
                  color=ADDED_COLOUR)

    axes.set_xlim(-half_side_cm - 1.6, half_side_cm + 1.9)
    axes.set_ylim(-half_side_cm - 1.0, half_side_cm + 1.6)
    axes.set_aspect("equal")
    axes.axis("off")


def draw_dot_scoreboard(axes, name, dot_x, dot_y):
    """Two bars for one dot -- how far sideways, how far up -- and which wall wins."""
    sideways = abs(dot_x)
    up_down = abs(dot_y)
    if sideways >= up_down:
        if dot_x > 0:
            verdict = "right wall"
        else:
            verdict = "left wall"
    else:
        if dot_y > 0:
            verdict = "top wall"
        else:
            verdict = "bottom wall"
    lead = abs(sideways - up_down)

    axes.barh([1], [sideways], color=SIDEWAYS_COLOUR, height=0.5)
    axes.barh([0], [up_down], color=UP_DOWN_COLOUR, height=0.5)
    axes.text(sideways + 0.15, 1, f"{sideways:.1f} cm sideways", va="center",
              fontsize=10, color=INK)
    axes.text(up_down + 0.15, 0, f"{up_down:.1f} cm up", va="center", fontsize=10,
              color=INK)
    if lead < 0.5:
        remark = f"almost a tie — only {lead * 10:.0f} mm in it"
        remark_colour = ADDED_COLOUR
    else:
        remark = f"clear: {lead * 10:.0f} mm ahead"
        remark_colour = INK_MUTED
    axes.text(0, 1.95, f"dot {name}  →  {verdict}", fontsize=12, weight="bold",
              color=INK)
    axes.text(0, -1.0, remark, fontsize=10, color=remark_colour)
    axes.set_xlim(0, 9.2)
    axes.set_ylim(-1.4, 2.4)
    axes.axis("off")


def slide_the_idea_in_two_dimensions(pdf):
    """The same rule with one dimension removed, in words anyone can follow."""
    figure = new_slide("The same idea, flattened: which wall is this dot on?",
                       "A box seen from above is just a square. Every dot is asked two "
                       "questions, and the bigger answer decides.")

    draw_box_from_above(figure.add_axes([0.04, 0.30, 0.30, 0.46]), 5.0)

    for index, (name, dot_x, dot_y) in enumerate(PLAIN_EXAMPLE_DOTS):
        axes = figure.add_axes([0.40, 0.60 - index * 0.165, 0.30, 0.13])
        draw_dot_scoreboard(axes, name, dot_x, dot_y)

    figure.text(0.40, 0.78, "How far from the middle, in each direction?", fontsize=13,
                weight="bold", color=INK, va="top")

    figure.text(0.74, 0.78, "That is the whole rule", fontsize=13, weight="bold",
                color=INK, va="top")
    paragraph(figure, 0.74, 0.725,
              "Stand in the middle of the box. Measure how far the dot is from you "
              "sideways, and how far it is up. Whichever is bigger tells you which wall "
              "the dot is nearly touching.\n\n"
              "A real box has three directions instead of two: three numbers, six "
              "walls. Nothing else changes.\n\n"
              "No other dot is consulted, and no edge is traced. Each dot answers "
              "on its own.",
              width_characters=36, font_size=11, colour=INK_SECONDARY)

    paragraph(figure, 0.04, 0.22,
              "Dot C is the awkward one. It sits in a corner, so it is almost the same "
              "distance from two walls and the rule nearly ties. That is fine: a dot in "
              "a corner is touching both walls anyway, so either answer puts it in "
              "almost the same place. On the real cube 8% of the dots are like C, and "
              "the rest win by a wide margin — the next slide measures it.",
              width_characters=150, font_size=11.5)
    footer(figure, "the rule in pipeline/core/box_mending.py, nearest_face()")
    pdf.savefig(figure)
    save_slide_png(figure, "08_the_idea_in_2d")
    plt.close(figure)


def draw_yaw_sweep(axes, assignment):
    """Panel 1: what every trial yaw costs, and where the fit settled."""
    axes.plot(assignment["yaw_degrees"], assignment["costs"], color=AFTER_COLOUR, lw=2)
    best_yaw = assignment["best_yaw_degrees"]
    axes.axvline(best_yaw, color=ADDED_COLOUR, lw=1.8, ls="--")
    axes.annotate(f"settles at {best_yaw:.0f}°", xy=(best_yaw, assignment["costs"].min()),
                  xytext=(best_yaw - 42, assignment["costs"].max() * 0.55),
                  fontsize=10, color=ADDED_COLOUR,
                  arrowprops=dict(arrowstyle="-|>", color=ADDED_COLOUR, lw=1.2))
    tidy_axes(axes, "1 · sweep the yaw to find the cube")
    axes.set_xlabel("yaw of the trial cube (degrees)", fontsize=10, color=INK_SECONDARY)
    axes.set_ylabel("mean squared distance to its surface", fontsize=9.5,
                    color=INK_SECONDARY)
    axes.set_xlim(0, 90)
    axes.set_yticks([])


def draw_assigned_faces(axes, capture, assignment):
    """Panel 2: the points in the cube's frame, coloured by the face each was given."""
    local_points_cm = capture["raw"]
    half_side_cm = capture["half_side_cm"]
    for face_axis in (0, 1, 2):
        for face_side in (1, -1):
            on_face = ((assignment["axis_index"] == face_axis)
                       & (assignment["side_sign"] == face_side))
            if not on_face.any():
                continue
            name = box_mending.FACE_NAMES[(face_axis, face_side)]
            screen_x, screen_y = isometric(local_points_cm[on_face, 0],
                                           local_points_cm[on_face, 1],
                                           local_points_cm[on_face, 2])
            axes.scatter(screen_x, screen_y, s=1.4, color=FACE_COLOURS[name], lw=0,
                         label=f"{name} ({int(on_face.sum()):,})")

    corners = []
    for corner_x in (-half_side_cm, half_side_cm):
        for corner_y in (-half_side_cm, half_side_cm):
            for corner_z in (-half_side_cm, half_side_cm):
                corners.append((corner_x, corner_y, corner_z))
    for first_index, first_corner in enumerate(corners):
        for second_corner in corners[first_index + 1:]:
            shared_axes = 0
            for first_value, second_value in zip(first_corner, second_corner):
                if first_value == second_value:
                    shared_axes += 1
            if shared_axes == 2:
                start_x, start_y = isometric(*first_corner)
                end_x, end_y = isometric(*second_corner)
                axes.plot([start_x, end_x], [start_y, end_y], color=INK, lw=0.9,
                          alpha=0.5, zorder=0)

    axes.set_aspect("equal")
    axes.axis("off")
    axes.set_title("2 · the largest coordinate names the face", fontsize=12, color=INK,
                   loc="left", pad=8)
    axes.legend(fontsize=8.5, frameon=False, loc="lower center", ncol=3,
                bbox_to_anchor=(0.5, -0.11), handletextpad=0.1, columnspacing=0.8,
                markerscale=5)


def draw_margin_histogram(axes, assignment):
    """Panel 3: how far the winning face led the runner-up, for every point."""
    margin_millimetres = assignment["margin_millimetres"]
    axes.hist(margin_millimetres, bins=70, range=(0, 50), color=BEFORE_COLOUR)
    axes.axvline(NEAR_EDGE_MILLIMETRES, color=ADDED_COLOUR, lw=1.8)
    near_edge_share = 100 * float(np.mean(margin_millimetres < NEAR_EDGE_MILLIMETRES))
    axes.text(0.97, 0.88,
              f"median lead {np.median(margin_millimetres):.0f} mm\n\n"
              f"{near_edge_share:.1f}% of points lead by\nunder "
              f"{NEAR_EDGE_MILLIMETRES:.0f} mm — those sit on an\nedge, where either "
              f"face is an\nequally good answer",
              transform=axes.transAxes, ha="right", va="top", fontsize=10,
              color=INK_SECONDARY, linespacing=1.7)
    tidy_axes(axes, "3 · how decisive each assignment is")
    axes.set_xlabel("how far the winning coordinate leads the runner-up (mm)",
                    fontsize=10, color=INK_SECONDARY)
    axes.set_ylabel("points", fontsize=10, color=INK_SECONDARY)


def slide_which_face(pdf, capture, assignment):
    """How a point is told which face it belongs to -- no neighbours consulted."""
    figure = new_slide("How each point is told which face it is on",
                       "A fair question when the cube is seen corner-on. The faces are "
                       "not worked out from edges or from neighbouring faces: the "
                       "cube's pose is fitted first, then each point is judged alone.")

    draw_yaw_sweep(figure.add_axes([0.05, 0.36, 0.23, 0.38]), assignment)
    draw_assigned_faces(figure.add_axes([0.345, 0.32, 0.22, 0.46]), capture, assignment)
    draw_margin_histogram(figure.add_axes([0.655, 0.36, 0.29, 0.38]), assignment)

    figure.text(0.05, 0.27, "The rule, in full", fontsize=13, weight="bold", color=INK,
                va="top")
    figure.text(0.05, 0.215,
                "rotate the point by minus the fitted yaw, move the cube's centre to the "
                "origin, then take whichever of |x|, |y|, |z| is largest:\n"
                "that axis is the face, and its sign is the side.",
                fontsize=11.5, color=INK, va="top", linespacing=1.8)
    paragraph(figure, 0.05, 0.125,
              "The fit itself solves five unknowns — yaw, centre x and y, base height "
              "and side — by minimising every point's distance to the trial cube's "
              "surface. The yaw is swept before any local fitting because a cube fitted "
              "45° out would wrap its own diagonal and read about 40% large.",
              width_characters=150, font_size=11, colour=INK_SECONDARY)
    footer(figure, "cube_fit.fit_cube and box_mending.nearest_face on output_test2_champ")
    pdf.savefig(figure)
    save_slide_png(figure, "09_which_face")
    plt.close(figure)


def draw_gridded_cube(axes, steps):
    """The cube seen from a corner above it, with the grid drawn on its three lit faces."""
    half = 5.0
    edges = np.linspace(-half, half, steps + 1)
    for face_name, face_axis, face_side in CUBE_VIEW_FACES:
        other_axes = []
        for candidate_axis in (0, 1, 2):
            if candidate_axis != face_axis:
                other_axes.append(candidate_axis)

        corner_points = []
        for first_sign, second_sign in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            corner = np.zeros(3)
            corner[face_axis] = face_side * half
            corner[other_axes[0]] = first_sign * half
            corner[other_axes[1]] = second_sign * half
            corner_points.append(isometric(*corner))
        axes.add_patch(plt.Polygon(corner_points, closed=True, facecolor="#f2f0ea",
                                   edgecolor=INK, lw=1.6, zorder=1))

        # One line per cell boundary, in both directions across the face.
        for moving_axis, fixed_axis in ((other_axes[0], other_axes[1]),
                                        (other_axes[1], other_axes[0])):
            for edge in edges:
                line_start = np.zeros(3)
                line_end = np.zeros(3)
                line_start[face_axis] = face_side * half
                line_end[face_axis] = face_side * half
                line_start[fixed_axis] = edge
                line_end[fixed_axis] = edge
                line_start[moving_axis] = -half
                line_end[moving_axis] = half
                start_x, start_y = isometric(*line_start)
                end_x, end_y = isometric(*line_end)
                axes.plot([start_x, end_x], [start_y, end_y], color=AFTER_COLOUR,
                          lw=0.35, alpha=0.75, zorder=2)

    axes.set_aspect("equal")
    axes.axis("off")
    axes.set_xlim(-11, 11)
    axes.set_ylim(-11, 13)


def draw_face_grid(axes, edges, occupied, title):
    """One face of the net: a square of cells, shaded by whether each held a point."""
    steps = len(edges) - 1
    cell_size = edges[1] - edges[0]
    for first_index in range(steps):
        for second_index in range(steps):
            if occupied[first_index, second_index]:
                cell_colour = "#cfe1f7"
            else:
                cell_colour = "#f6ddd0"
            axes.add_patch(Rectangle((edges[first_index], edges[second_index]),
                                     cell_size, cell_size, facecolor=cell_colour,
                                     edgecolor="#ffffff", lw=0.2))
    axes.set_xlim(edges[0], edges[-1])
    axes.set_ylim(edges[0], edges[-1])
    axes.set_aspect("equal")
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_color(INK)
        spine.set_linewidth(1.2)
    axes.set_title(title, fontsize=9.5, color=INK, loc="center", pad=3)


def slide_how_the_cube_is_sliced(pdf, bad_capture):
    """Where the cube's cells come from: a 4 mm grid laid on each of its six faces."""
    figure = new_slide("How the cube is sliced: a 4 mm grid on each of its six faces",
                       "The cube is never cut into blocks or layers. Each face is "
                       "gridded on its own, and only on the surface.")

    steps = len(face_cell_occupancy(bad_capture, 2, -1)[0]) - 1
    axes_cube = figure.add_axes([0.03, 0.30, 0.33, 0.46])
    draw_gridded_cube(axes_cube, steps)
    axes_cube.set_title(f"the 10 cm cube, {steps} × {steps} cells per face",
                        fontsize=12, color=INK, loc="left", pad=6)
    axes_cube.annotate("each cell is 4 × 4 mm",
                       xy=isometric(5.0, -1.2, 1.2), xytext=(6.2, 8.4),
                       fontsize=10, color=INK_SECONDARY,
                       arrowprops=dict(arrowstyle="-|>", color=INK_MUTED, lw=1.2))

    # The cube unfolded: the four side faces in a row, the top above and bottom below.
    net_positions = {("top", 2, 1): (1, 2), ("x-", 0, -1): (0, 1), ("y+", 1, 1): (1, 1),
                     ("x+", 0, 1): (2, 1), ("y-", 1, -1): (3, 1),
                     ("bottom", 2, -1): (1, 0)}
    net_left = 0.40
    net_bottom = 0.27
    tile_width = 0.105
    tile_height = 0.160
    total_cells = 0
    total_filled = 0
    for (face_name, face_axis, face_side), (column, row) in net_positions.items():
        edges, occupied = face_cell_occupancy(bad_capture, face_axis, face_side)
        filled = int(occupied.sum())
        cells = occupied.size
        total_cells += cells
        total_filled += filled
        axes_face = figure.add_axes([net_left + column * tile_width,
                                     net_bottom + row * tile_height,
                                     tile_width * 0.88, tile_height * 0.88])
        draw_face_grid(axes_face, edges, occupied,
                       f"{face_name} · {100 * filled / cells:.0f}%")

    figure.text(0.40, 0.815, "the same cube unfolded, one square per cell",
                fontsize=12, color=INK, va="top")
    figure.text(0.40, 0.783,
                "shaded by what test2_champ's capture actually reached",
                fontsize=10, color=INK_MUTED, va="top")

    figure.text(0.845, 0.72, "Reading it", fontsize=12.5, weight="bold", color=INK,
                va="top")
    figure.add_artist(plt.Rectangle((0.847, 0.655), 0.018, 0.024, facecolor="#cfe1f7",
                                    edgecolor=INK, lw=0.6, transform=figure.transFigure))
    figure.text(0.872, 0.681, "a cell that held\na point", fontsize=10,
                color=INK_SECONDARY, va="top", linespacing=1.6)
    figure.add_artist(plt.Rectangle((0.847, 0.555), 0.018, 0.024, facecolor="#f6ddd0",
                                    edgecolor=INK, lw=0.6, transform=figure.transFigure))
    figure.text(0.872, 0.581, "an empty cell —\nthe filler drops\none point in",
                fontsize=10, color=INK_SECONDARY, va="top", linespacing=1.6)
    paragraph(figure, 0.845, 0.45,
              f"{total_filled:,} of the {total_cells:,} cells held a point, so "
              f"{total_cells - total_filled:,} were filled.",
              width_characters=22, font_size=10, colour=INK_SECONDARY)

    paragraph(figure, 0.04, 0.20,
              "Why a grid and not a stack of slices: the cube's error is that parts of "
              "its SURFACE were never photographed, and a hole in a surface is what makes "
              "Poisson reconstruction tunnel. A flat grid on each face finds exactly those "
              "holes; cutting the cube into layers would not say which patch of which face "
              "is missing. The bottom face looks at the floor, so it is always the "
              "thinnest — 43% here — and it is most of the filler's work.",
              width_characters=152, font_size=11)
    footer(figure, "pipeline/core/box_mending.py run live on output_test2_champ")
    pdf.savefig(figure)
    save_slide_png(figure, "10_how_the_cube_is_sliced")
    plt.close(figure)


# --------------------------------------------------------------------- slide 9

def slide_mending_effect(pdf, bad_capture, sound_capture):
    """What mending is worth, and the honest answer: usually almost nothing."""
    figure = new_slide("What mending is worth — and when it does nothing",
                       "The step earns its keep on a capture that went wrong, and is "
                       "close to a no-op on one that went right.")

    axes = figure.add_axes([0.07, 0.42, 0.36, 0.34])
    labels = ["bad capture\ntest2_champ\n(cube corner-on)",
              "sound capture\ntest6\n(cube seen all round)"]
    added_counts = [bad_capture["report"]["added"], sound_capture["report"]["added"]]
    worst_coverage = []
    for capture in (bad_capture, sound_capture):
        thinnest_percent = 100.0
        for face in capture["report"]["coverage"].values():
            covered_percent = 100 * face["covered"] / face["cells"]
            if covered_percent < thinnest_percent:
                thinnest_percent = covered_percent
        worst_coverage.append(thinnest_percent)
    positions = np.arange(len(labels))
    axes.bar(positions, added_counts, width=0.45, color=[ADDED_COLOUR, BEFORE_COLOUR])
    label_height = max(added_counts) * 0.12
    for position, count, coverage_percent in zip(positions, added_counts, worst_coverage):
        axes.text(position, count + 30, f"{count:,} points added", ha="center",
                  fontsize=11.5, color=INK, weight="bold")
        if count > 400:
            inner_label_colour = "white"
        else:
            inner_label_colour = INK
        axes.text(position, label_height, f"thinnest face\n{coverage_percent:.0f}% covered",
                  ha="center", va="center", fontsize=10, color=inner_label_colour,
                  linespacing=1.5)
    axes.set_xticks(positions)
    axes.set_xticklabels(labels, fontsize=10)
    axes.set_ylim(0, max(added_counts) * 1.3)
    tidy_axes(axes, "how much the filler had to invent")
    axes.set_ylabel("points dropped into empty cells", fontsize=10.5, color=INK_SECONDARY)

    figure.text(0.50, 0.79, "Measured consequences", fontsize=13, weight="bold",
                color=INK, va="top")
    bullet_list(figure, 0.50, 0.735, [
        "Poisson closes on the mended cube instead of tunnelling, so Stage 4 stops "
        "falling back to the alpha ladder.",
        "test2_sunshine, a sound capture: the cube's mesh went 1000.0 → 1004 cm³. "
        "Four parts in a thousand.",
        "test2_champ's alpha wrap had been reading 9.1% more volume than its own "
        "points described. That term is gone.",
        "On a sound capture the step is invisible in the result — which is the "
        "point. It is a guard, not a correction.",
    ], line_gap=0.055, font_size=11.5, width_characters=56)

    figure.text(0.07, 0.28, "What it is NOT", fontsize=13, weight="bold", color=INK,
                va="top")
    bullet_list(figure, 0.07, 0.225, [
        "Not a way to force the cube to 10 cm — the fit is 10 cm by construction, and "
        "the points keep their own spread around it.",
        "Not a rescue for a barely photographed cube: filling a face that is 43% "
        "covered is still mostly guessing. Re-shoot instead.",
        "Not applied to the limb, whose true shape is the unknown we are after.",
    ], line_gap=0.055, font_size=11.5, width_characters=126)
    footer(figure, "box_mending.py on output_test2_champ and output_test6; "
                   "EXPERIMENT_LOG §20")
    pdf.savefig(figure)
    save_slide_png(figure, "11_mending_effect")
    plt.close(figure)


# -------------------------------------------------------------------- slide 10

def slide_results(pdf):
    """The before/after chart for every capture that has a usable truth."""
    figure = new_slide("What the two changes measured",
                       "Signed error against each capture's own ground truth. Positive "
                       "means the pipeline read more volume than the truth did.")

    captures = [("test1_5", 4.8, 0.1), ("test1_6", 6.9, 0.2), ("test2_keng", 6.9, 1.7),
                ("test2_sunshine\nshaved", None, 2.2), ("test2_champ\nshaved", None, -0.6)]
    axes = figure.add_axes([0.06, 0.34, 0.58, 0.42])
    bar_width = 0.36
    for index, (_, before, after) in enumerate(captures):
        if before is not None:
            axes.bar(index - bar_width / 2, before, width=bar_width, color=BEFORE_COLOUR)
            axes.text(index - bar_width / 2, before + 0.3, f"+{before:.1f}%", ha="center",
                      fontsize=10.5, color=INK_SECONDARY)
        axes.bar(index + bar_width / 2, after, width=bar_width, color=AFTER_COLOUR)
        if after >= 0:
            label_offset = 0.3
        else:
            label_offset = -0.95
        axes.text(index + bar_width / 2, after + label_offset, f"{after:+.1f}%",
                  ha="center", fontsize=10.5, color=INK, weight="bold")
    axes.axhline(0, color=TRUTH_COLOUR, lw=1.4)
    axes.set_xticks(np.arange(len(captures)))
    capture_names = []
    for name, _, _ in captures:
        capture_names.append(name)
    axes.set_xticklabels(capture_names, fontsize=10.5)
    axes.set_ylim(-2.4, 8.8)
    tidy_axes(axes, "error against truth, before and after both changes")
    axes.set_ylabel("error (%)", fontsize=10.5, color=INK_SECONDARY)
    axes.bar(0, 0, color=BEFORE_COLOUR, label="before — cut at the stripe centres")
    axes.bar(0, 0, color=AFTER_COLOUR, label="after — inner-edge cut + mending")
    axes.legend(fontsize=10.5, frameon=False, loc="upper right")
    figure.text(0.06, 0.26,
                "The two shaved captures have no 'before': they were only ever shot "
                "after the change.",
                fontsize=10.5, color=INK_MUTED, va="top")

    figure.text(0.69, 0.76, "Five captures", fontsize=13, weight="bold", color=INK,
                va="top")
    figure.text(0.69, 0.71, "1.0%", fontsize=44, weight="bold", color=AFTER_COLOUR,
                va="top")
    figure.text(0.69, 0.615, "mean absolute error", fontsize=12, color=INK_SECONDARY,
                va="top")
    figure.text(0.69, 0.555, "+0.7%", fontsize=22, weight="bold", color=INK, va="top")
    figure.text(0.69, 0.505, "mean signed bias — no systematic\nover-reading left",
                fontsize=11, color=INK_SECONDARY, va="top", linespacing=1.6)
    paragraph(figure, 0.69, 0.41,
              "All five are captures where the truth and the cameras see the same "
              "surface: a shaved or hairless leg measured with a tape, or a hairy leg "
              "measured by water displacement.",
              width_characters=38, font_size=11, colour=INK_SECONDARY)
    footer(figure, "EXPERIMENT_LOG §20; run logs of 2026-10-09")
    pdf.savefig(figure)
    save_slide_png(figure, "12_results")
    plt.close(figure)


# -------------------------------------------------------------------- slide 11

def slide_hair(pdf):
    """The other finding of the day: hair, and why the fitted version was wrong."""
    figure = new_slide("The other finding: leg hair, and a lesson about fitting",
                       "A tape flattens hair and reads the skin. The cameras see the "
                       "outside of it. On a hairy leg the two truths are not the same "
                       "surface.")

    axes = figure.add_axes([0.06, 0.42, 0.33, 0.34])
    labels = ["champ", "sunshine"]
    hairy_errors = [23.0, 10.2]
    shaved_errors = [-0.6, 2.2]
    positions = np.arange(len(labels))
    bar_width = 0.34
    axes.bar(positions - bar_width / 2, hairy_errors, width=bar_width, color=ADDED_COLOUR,
             label="hairy leg, tape truth")
    axes.bar(positions + bar_width / 2, shaved_errors, width=bar_width, color=AFTER_COLOUR,
             label="shaved, re-shot, re-taped")
    for position, hairy, shaved in zip(positions, hairy_errors, shaved_errors):
        axes.text(position - bar_width / 2, hairy + 0.8, f"+{hairy:.1f}%", ha="center",
                  fontsize=11, color=INK, weight="bold")
        if shaved >= 0:
            shaved_label_offset = 0.8
        else:
            shaved_label_offset = -2.6
        axes.text(position + bar_width / 2, shaved + shaved_label_offset,
                  f"{shaved:+.1f}%", ha="center", fontsize=11, color=INK, weight="bold")
    axes.axhline(0, color=TRUTH_COLOUR, lw=1.4)
    axes.set_xticks(positions)
    axes.set_xticklabels(labels, fontsize=11)
    axes.set_ylim(-4, 28)
    tidy_axes(axes, "shaving one leg and capturing it again")
    axes.set_ylabel("error against tape truth (%)", fontsize=10.5, color=INK_SECONDARY)
    axes.legend(fontsize=9.5, frameon=False, loc="upper right")

    figure.text(0.45, 0.76, "What the shave actually measured", fontsize=13,
                weight="bold", color=INK, va="top")
    draw_table(figure, (0.45, 0.55, 0.50, 0.17),
               ["region of the limb", "girth removed", "implied hair"],
               [["lower half", "+0.11 cm", "0.02 cm"],
                ["upper half, where the hair was", "+0.49 cm", "0.08 cm"],
                ["peak, 70–95% along", "+0.80 to +0.89 cm", "0.13–0.14 cm"]],
               [0.52, 0.26, 0.22], font_size=10.5)
    paragraph(figure, 0.45, 0.51,
              "So VGGT reads 0.8–1.4 mm of apparent radius off hair that stands 4–8 mm: "
              "it sees mostly through it, sits a little proud, and only where the hair "
              "is.",
              width_characters=68, font_size=11, colour=INK_SECONDARY)

    figure.text(0.06, 0.37, "The lesson", fontsize=13, weight="bold", color=INK,
                va="top")
    paragraph(figure, 0.06, 0.315,
              "Earlier the same day a hair term was added to the tape truth and solved "
              "for. It 'explained' sunshine at 0.41 cm of hair and champ at 0.90 cm — "
              "both inside the ranges measured on those legs by hand, which looked like "
              "confirmation and was not: one free parameter against one target always "
              "fits. The shave is what actually measured it.\n\n"
              "A bad capture still costs more than hair does. The first shaved upload "
              "read +9.6% and a re-shoot of the same leg against the same tape read "
              "+2.2% — 7.3% apart, with nothing about the subject changed in between.",
              width_characters=130, font_size=11.5)
    footer(figure, "EXPERIMENT_LOG §20; the test2_*_hairless tape profiles")
    pdf.savefig(figure)
    save_slide_png(figure, "13_hair")
    plt.close(figure)


# -------------------------------------------------------------------- slide 12

def slide_where_we_stand(pdf):
    """Honest closing slide: what is settled, what is not."""
    figure = new_slide("Where this leaves us",
                       "Both changes are on by default on keng-branch at 5ab597f, and "
                       "either can be switched off for a single run.")

    figure.text(0.05, 0.79, "Settled", fontsize=14, weight="bold", color=AFTER_COLOUR,
                va="top")
    bullet_list(figure, 0.05, 0.735, [
        "Where the cutting plane lands on a 2 cm stripe was the largest error in the "
        "pipeline, and it now has a definition: the inner edges, which is what the "
        "tape measures.",
        "The reference cube never held 6% of error. Its volume was already right to "
        "about 0.4% on a sound capture.",
        "On a capture whose truth and cameras see the same surface, the pipeline reads "
        "within about 1%.",
        "Leg hair is a truth-definition problem, not a model problem. Shave the band "
        "region, or measure the truth by water displacement.",
    ], line_gap=0.055, font_size=12, width_characters=104)

    figure.text(0.05, 0.40, "Still open", fontsize=14, weight="bold", color=ADDED_COLOUR,
                va="top")
    bullet_list(figure, 0.05, 0.345, [
        "Four older water-truth captures read −5.9%, +7.1%, −13.1% and −10.8%. Where "
        "the water line sat on the band was never written down, so their truth belongs "
        "to a different plane than the one we now cut on.",
        "Repeatability between two captures of the same leg is 7.3%. Capture quality "
        "now dominates everything else, and nothing in the pipeline measures it.",
        "Stage 0 still refuses any frame that does not show the whole cube. Three "
        "captures in a row hit that gate from poses where the cube cannot fit in "
        "frame; it should warn, not stop, once enough frames carry it.",
    ], line_gap=0.055, font_size=12, width_characters=104)
    footer(figure, "EXPERIMENT_LOG §21")
    pdf.savefig(figure)
    save_slide_png(figure, "14_where_we_stand")
    plt.close(figure)


# --------------------------------------------------------------------- plumbing

def save_slide_png(figure, name):
    """Also write the slide on its own, so single slides can be shown in chat."""
    SLIDE_PNG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    figure.savefig(SLIDE_PNG_DIRECTORY / f"{name}.png", dpi=130, facecolor=SURFACE)


def build_span_rows():
    """The centre-to-centre and inner-to-inner spans of every run of the new pipeline."""
    runs = [("test2_champ_hairless", "output_test2_champ_hairless"),
            ("test2_sunshine_hairless", "output_test2_sunshine_hairless"),
            ("test2_keng", "output_test2_keng_v5"),
            ("test1_6", "output_test1_6_v5"),
            ("test1_5", "output_test1_5_v5")]
    rows = []
    for label, directory_name in runs:
        run_directory = PROJECT_ROOT / directory_name
        if not run_directory.exists():
            continue
        measured = measure_band_stripes(run_directory)
        moved_cm = measured["centre_span_cm"] - measured["inner_span_cm"]
        rows.append([label,
                     f"{measured['centre_span_cm']:.2f} cm",
                     f"{measured['inner_span_cm']:.2f} cm",
                     f"−{moved_cm:.2f} cm"])
    return rows


def main():
    """Render every slide into one PDF, and each slide into its own PNG."""
    stripe_data = measure_band_stripes(NEW_PIPELINE_RUN)
    span_rows = build_span_rows()
    bad_capture = mend_one_box(BAD_CAPTURE_RUN)
    sound_capture = mend_one_box(SOUND_CAPTURE_RUN)
    assignment = face_assignment(bad_capture)

    with PdfPages(OUTPUT_PDF) as pdf:
        slide_title(pdf)
        slide_what_changed(pdf)
        slide_band_is_a_stripe(pdf, stripe_data)
        slide_inner_edge_fix(pdf, span_rows)
        slide_why_the_cube_matters(pdf)
        slide_two_defects(pdf, bad_capture)
        slide_the_four_steps(pdf, bad_capture)
        slide_the_idea_in_two_dimensions(pdf)
        slide_which_face(pdf, bad_capture, assignment)
        slide_how_the_cube_is_sliced(pdf, bad_capture)
        slide_mending_effect(pdf, bad_capture, sound_capture)
        slide_results(pdf)
        slide_hair(pdf)
        slide_where_we_stand(pdf)

    print(f"Wrote {OUTPUT_PDF}")
    print(f"Wrote {SLIDE_COUNTER['number']} slide PNGs to {SLIDE_PNG_DIRECTORY}")


if __name__ == "__main__":
    main()
