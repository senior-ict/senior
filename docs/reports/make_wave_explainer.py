"""Show how waves around a ring make a circle, a shifted circle, an oval and a rounded triangle.

Top row: radius against angle (the ring unrolled). Bottom row: the same radius
drawn around a centre. Last column: made-up points shaped like test6's slice
(an oval, a spur and a gap), the smooth curve, and the points far from it.

    python docs/reports/make_wave_explainer.py
"""
import pathlib

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUTPUT = HERE / "2026-09-21_wave_explainer.png"
SURFACE = "#fcfcfb"
CURVE_COLOUR = "#2a78d6"
POINT_COLOUR = "#2f3a44"
UNUSUAL_COLOUR = "#b3261e"
TOLERANCE_COLOUR = "#cfe0f6"
MEAN_RADIUS = 4.5


def radius_curve(angles, wave_sizes):
    """Mean radius plus one cosine wave per entry: wave_sizes[k] is the size of the wave going k times around."""
    radii = np.full_like(angles, MEAN_RADIUS)
    for wave_number, size in wave_sizes.items():
        radii = radii + size * np.cos(wave_number * angles)
    return radii


def draw_column(unrolled_axes, ring_axes, angles, radii, title):
    """Unrolled graph on top, ring below, for one radius curve."""
    unrolled_axes.plot(np.degrees(angles), radii, color=CURVE_COLOUR, linewidth=2)
    unrolled_axes.set_ylim(3.0, 6.3)
    unrolled_axes.set_xlim(0, 360)
    unrolled_axes.set_xticks([0, 180, 360])
    unrolled_axes.set_title(title, fontsize=11)
    unrolled_axes.grid(alpha=0.25)
    ring_axes.plot(radii * np.cos(angles), radii * np.sin(angles), color=CURVE_COLOUR, linewidth=2)
    ring_axes.plot([0], [0], marker="+", color=UNUSUAL_COLOUR, markersize=10)
    ring_axes.set_xlim(-6.5, 6.5)
    ring_axes.set_ylim(-6.5, 6.5)
    ring_axes.set_aspect("equal")
    ring_axes.set_xticks([])
    ring_axes.set_yticks([])


def main():
    """Five columns: circle, one wave, two waves, three waves, and a real-looking slice."""
    angles = np.linspace(0, 2 * np.pi, 400)
    columns = [
        ("flat line = circle", {}),
        ("+ 1 wave per turn\n= circle pushed sideways", {1: 0.6}),
        ("+ 2 waves per turn\n= oval", {2: 0.7}),
        ("+ 3 waves per turn\n= rounded triangle", {3: 0.4}),
    ]
    figure, axes_grid = plt.subplots(2, 5, figsize=(16, 6.4), facecolor=SURFACE,
                                     gridspec_kw={"height_ratios": [1, 1.4]})
    for column, (title, wave_sizes) in enumerate(columns):
        draw_column(axes_grid[0, column], axes_grid[1, column], angles, radius_curve(angles, wave_sizes), title)
    axes_grid[0, 0].set_ylabel("distance from centre (cm)", fontsize=10)
    axes_grid[1, 0].set_ylabel("the same, drawn around the centre", fontsize=10)

    # A slice like test6's: an oval plus a little of wave 3, with noise, a spur and a gap.
    random_generator = np.random.default_rng(1)
    smooth = radius_curve(angles, {2: 0.44, 3: 0.05})
    point_angles = np.sort(random_generator.uniform(0, 2 * np.pi, 220))
    in_gap = (point_angles > np.radians(75)) & (point_angles < np.radians(100))
    point_angles = point_angles[~in_gap]
    point_radii = radius_curve(point_angles, {2: 0.44, 3: 0.05}) + random_generator.normal(0, 0.05, len(point_angles))
    spur = (point_angles > np.radians(40)) & (point_angles < np.radians(65))
    point_radii[spur] += np.linspace(0.2, 1.3, spur.sum())
    tolerance = 0.02 * radius_curve(point_angles, {2: 0.44, 3: 0.05})
    unusual = np.abs(point_radii - radius_curve(point_angles, {2: 0.44, 3: 0.05})) > tolerance

    unrolled_axes = axes_grid[0, 4]
    unrolled_axes.fill_between(np.degrees(angles), smooth * 0.98, smooth * 1.02, color=TOLERANCE_COLOUR, lw=0)
    unrolled_axes.plot(np.degrees(angles), smooth, color=CURVE_COLOUR, linewidth=2)
    unrolled_axes.scatter(np.degrees(point_angles[~unusual]), point_radii[~unusual], s=5, color=POINT_COLOUR)
    unrolled_axes.scatter(np.degrees(point_angles[unusual]), point_radii[unusual], s=9, color=UNUSUAL_COLOUR)
    unrolled_axes.set_ylim(3.0, 6.3)
    unrolled_axes.set_xlim(0, 360)
    unrolled_axes.set_xticks([0, 180, 360])
    unrolled_axes.set_title("made-up slice like test6's:\nred = far from the curve = unusual", fontsize=11)
    unrolled_axes.grid(alpha=0.25)
    ring_axes = axes_grid[1, 4]
    ring_axes.plot(smooth * np.cos(angles), smooth * np.sin(angles), color=CURVE_COLOUR, linewidth=2)
    ring_axes.scatter(point_radii[~unusual] * np.cos(point_angles[~unusual]),
                      point_radii[~unusual] * np.sin(point_angles[~unusual]), s=5, color=POINT_COLOUR)
    ring_axes.scatter(point_radii[unusual] * np.cos(point_angles[unusual]),
                      point_radii[unusual] * np.sin(point_angles[unusual]), s=9, color=UNUSUAL_COLOUR)
    ring_axes.plot([0], [0], marker="+", color=UNUSUAL_COLOUR, markersize=10)
    ring_axes.set_xlim(-6.5, 6.5)
    ring_axes.set_ylim(-6.5, 6.5)
    ring_axes.set_aspect("equal")
    ring_axes.set_xticks([])
    ring_axes.set_yticks([])
    for column in range(5):
        axes_grid[0, column].set_xlabel("angle (degrees)", fontsize=9)
    figure.tight_layout()
    figure.savefig(OUTPUT, dpi=100, facecolor=SURFACE)
    print(OUTPUT)


if __name__ == "__main__":
    main()
