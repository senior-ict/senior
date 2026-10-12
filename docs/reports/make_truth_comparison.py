"""Compare the current pipeline against ground truth: volume between the bands, and band girths.

Left: each capture's truth and measured volume, joined by a line, with the
error beside it. Right: every band girth against the tape that measured it,
with the line where they would agree.

Numbers are from the skeleton-on reruns (work/<capture>_skel_on), 21-23
September 2026: Stage 6's volumes.csv and the circumference it prints at each
cutting plane.

    python docs/reports/make_truth_comparison.py
"""
import pathlib

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUTPUT = HERE / "2026-09-23_current_vs_truth.png"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
RULE = "#e4e2dc"
TRUTH_COLOUR = "#8a8882"
MEASURED_COLOUR = "#2a78d6"

# capture, how the truth was measured, truth cm3, measured cm3
VOLUMES = [
    ("test6", "tape", 1398.6, 1485.2),
    ("test5", "water", 2070.0, 2167.6),
    ("0_right", "water", 1830.0, 1743.5),
    ("1_left", "water", 1600.0, 1591.1),
    ("6_left", "water", 2800.0, 2647.2),
    ("2_left", "water", 1050.0, 1180.2),
]

# capture, tape lower, tape upper, measured lower, measured upper (cm)
GIRTHS = [
    ("test6", 19.0, 28.0, 19.51, 29.28),
    ("test5", 22.0, 32.5, 22.12, 32.86),
    ("0_right", 20.5, 29.5, 18.60, 29.42),
    ("1_left", 21.5, 32.0, 19.67, 30.14),
    ("6_left", 24.3, 35.0, 21.87, 34.96),
    ("2_left", 18.5, 27.5, 18.74, 27.56),
]


def draw_volume_panel(axes):
    """Truth and measured volume per capture, joined by a line, newest capture at the top."""
    positions = np.arange(len(VOLUMES))[::-1]
    for position, (name, truth_kind, truth, measured) in zip(positions, VOLUMES):
        axes.plot([truth, measured], [position, position], color=RULE, linewidth=2.5, zorder=1)
        axes.scatter([truth], [position], s=70, color=TRUTH_COLOUR, zorder=2)
        axes.scatter([measured], [position], s=70, color=MEASURED_COLOUR, zorder=3)
        error_percent = 100 * (measured / truth - 1)
        axes.text(2950, position, f"{error_percent:+.1f}%", fontsize=12, va="center",
                  color=INK, weight="bold" if abs(error_percent) > 10 else "normal")
        axes.text(3300, position, truth_kind, fontsize=10, va="center", color=INK_SECONDARY)
    axes.set_yticks(positions)
    axes.set_yticklabels([name for name, _, _, _ in VOLUMES], fontsize=12)
    axes.set_xlim(800, 3550)
    axes.set_xticks([1000, 1500, 2000, 2500, 3000])
    axes.set_xlabel("volume between the bands (cm³)", fontsize=12)
    axes.set_title("Volume against ground truth", fontsize=14, weight="bold", loc="left", pad=26)
    axes.grid(axis="x", alpha=0.25)
    axes.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        axes.spines[spine].set_visible(False)
    axes.scatter([], [], s=70, color=TRUTH_COLOUR, label="truth (water or tape)")
    axes.scatter([], [], s=70, color=MEASURED_COLOUR, label="pipeline")
    axes.legend(fontsize=11, frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2)


def draw_girth_panel(axes):
    """Every band girth against the tape, with the agreement line."""
    limits = (17, 37)
    axes.plot(limits, limits, color=TRUTH_COLOUR, linewidth=1.2, linestyle=(0, (4, 3)), zorder=1)
    axes.text(34.2, 34.9, "agreement", fontsize=10, color=TRUTH_COLOUR, rotation=45,
              ha="center", va="bottom")
    for name, tape_lower, tape_upper, measured_lower, measured_upper in GIRTHS:
        axes.scatter([tape_lower, tape_upper], [measured_lower, measured_upper], s=55,
                     color=MEASURED_COLOUR, zorder=3)
        for tape_value, measured_value in ((tape_lower, measured_lower), (tape_upper, measured_upper)):
            if abs(measured_value - tape_value) > 1.5:
                axes.annotate(name, (tape_value, measured_value), textcoords="offset points",
                              xytext=(9, -11), fontsize=9.5, color=INK_SECONDARY)
    axes.set_xlim(*limits)
    axes.set_ylim(*limits)
    axes.set_aspect("equal")
    axes.set_xlabel("tape girth at the band (cm)", fontsize=12)
    axes.set_ylabel("pipeline girth (cm)", fontsize=12)
    axes.set_title("Band girth against the tape", fontsize=14, weight="bold", loc="left")
    axes.grid(alpha=0.25)
    axes.set_axisbelow(True)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)


def main():
    """Draw both panels and print the summary numbers."""
    figure = plt.figure(figsize=(14, 6.2), facecolor=SURFACE)
    volume_axes = figure.add_axes([0.075, 0.14, 0.52, 0.74])
    volume_axes.set_facecolor(SURFACE)
    draw_volume_panel(volume_axes)
    girth_axes = figure.add_axes([0.70, 0.14, 0.28, 0.74])
    girth_axes.set_facecolor(SURFACE)
    draw_girth_panel(girth_axes)

    volume_errors = np.array([100 * (measured / truth - 1) for _, _, truth, measured in VOLUMES])
    girth_errors = []
    for _, tape_lower, tape_upper, measured_lower, measured_upper in GIRTHS:
        girth_errors.append(100 * (measured_lower / tape_lower - 1))
        girth_errors.append(100 * (measured_upper / tape_upper - 1))
    girth_errors = np.array(girth_errors)
    figure.text(0.075, 0.035,
                f"Volume: mean error {np.abs(volume_errors).mean():.1f}% ignoring sign, "
                f"{volume_errors.mean():+.1f}% with sign, worst {volume_errors.max():+.1f}% (2_left).     "
                f"Girth: mean {np.abs(girth_errors).mean():.1f}% ignoring sign, {girth_errors.mean():+.1f}% with sign.",
                fontsize=11.5, color=INK)
    figure.savefig(OUTPUT, dpi=110, facecolor=SURFACE)
    print(OUTPUT)
    print(f"volume errors: {np.round(volume_errors, 1)}")
    print(f"girth errors:  {np.round(girth_errors, 1)}")


if __name__ == "__main__":
    main()
