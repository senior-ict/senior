"""Turn a tape circumference profile into a ground-truth volume.

A tape gives the circumference at a list of heights. Between two neighbouring
heights the limb is treated as a truncated cone (a frustum), so the volume of
one slab is

    volume = height * (lower^2 + lower * upper + upper^2) / (12 * pi)

with the circumferences in centimetres, which is the cone formula rewritten in
terms of circumference instead of radius.

Three sums are printed, because the choice of rule is the first thing anyone
asks about. On a smooth limb they agree to a fraction of a percent, so a jump
between two profiles of the same limb means the measurements changed, not the
arithmetic:

    frustum   the cone rule above, the number this project quotes
    disc      each slab a cylinder of the mean circumference, a lower bound
    simpson   the parabolic rule, only valid on an evenly spaced profile

The frustum number is an UPPER bound on the real limb, because a tape measures
the perimeter and a circle holds more area than any other shape of the same
perimeter. A limb with an oval cross-section of axis ratio 1.1 reads about 0.2%
high this way, 1.2 about 0.8% high.

    python docs/experiments/2026-09_test_captures/tape_volume.py <profile.csv> [more.csv ...]
"""
import argparse
import csv
import math
import pathlib


def read_profile(path):
    """Read a profile CSV and return (subject, [(height_cm, circumference_cm), ...]) sorted by height."""
    rows = []
    subject = pathlib.Path(path).stem
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            subject = row.get("subject", subject)
            rows.append((float(row["height_cm"]), float(row["circumference_cm"])))
    rows.sort(key=lambda entry: entry[0])
    return subject, rows


def frustum_volume(profile):
    """Sum of truncated cones between neighbouring measurements, in cm3."""
    total = 0.0
    for index in range(len(profile) - 1):
        lower_height, lower_circumference = profile[index]
        upper_height, upper_circumference = profile[index + 1]
        slab_height = upper_height - lower_height
        squares = (lower_circumference ** 2
                   + lower_circumference * upper_circumference
                   + upper_circumference ** 2)
        total += slab_height * squares / (12.0 * math.pi)
    return total


def disc_volume(profile):
    """Sum of cylinders of the mean circumference of each slab, in cm3."""
    total = 0.0
    for index in range(len(profile) - 1):
        lower_height, lower_circumference = profile[index]
        upper_height, upper_circumference = profile[index + 1]
        mean_circumference = (lower_circumference + upper_circumference) / 2.0
        area = mean_circumference ** 2 / (4.0 * math.pi)
        total += (upper_height - lower_height) * area
    return total


def simpson_volume(profile):
    """Simpson's rule over the area profile, or None when the heights are not evenly spaced in an even count of slabs."""
    heights = [height for height, _ in profile]
    spacings = [heights[index + 1] - heights[index] for index in range(len(heights) - 1)]
    if len(spacings) % 2 == 1:
        return None
    first_spacing = spacings[0]
    for spacing in spacings:
        if abs(spacing - first_spacing) > 1e-9:
            return None
    areas = [circumference ** 2 / (4.0 * math.pi) for _, circumference in profile]
    total = areas[0] + areas[-1]
    for index in range(1, len(areas) - 1):
        total += areas[index] * (4 if index % 2 == 1 else 2)
    return total * first_spacing / 3.0


def report(path):
    """Print every volume rule for one profile."""
    subject, profile = read_profile(path)
    if len(profile) < 2:
        raise SystemExit(f"{path}: needs at least two measurements")
    span = profile[-1][0] - profile[0][0]
    frustum = frustum_volume(profile)
    disc = disc_volume(profile)
    simpson = simpson_volume(profile)

    print(f"{subject}  ({pathlib.Path(path).name})")
    print(f"  measurements   {len(profile)} over {span:.1f} cm "
          f"({span / (len(profile) - 1):.2f} cm apart)")
    circumferences = [circumference for _, circumference in profile]
    print(f"  circumference  {min(circumferences):.1f} to {max(circumferences):.1f} cm")
    print(f"  frustum        {frustum:.1f} cm3   <- quote this one")
    print(f"  disc           {disc:.1f} cm3   ({100 * (disc / frustum - 1):+.2f}% vs frustum)")
    if simpson is None:
        print("  simpson        not applicable (uneven spacing or an odd slab count)")
    else:
        print(f"  simpson        {simpson:.1f} cm3   ({100 * (simpson / frustum - 1):+.2f}% vs frustum)")
    return frustum


def main():
    """Report every profile named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("profiles", nargs="+", help="profile CSVs: subject,side,height_cm,circumference_cm")
    arguments = parser.parse_args()
    for path in arguments.profiles:
        report(path)


if __name__ == "__main__":
    main()
