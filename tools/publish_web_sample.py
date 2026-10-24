"""Turn one pipeline run into a sample folder the web app can serve.

The web app reads a fixed set of file names out of
`web/public/samples/<name>/`. A run writes different names in different
folders, so this copies and renames rather than asking either side to change:

    mesh/segmented_obj.ply   ->  leg_mesh.ply
    mesh/box.ply             ->  box_mesh.ply
    mesh/scene.ply           ->  scene_mesh.ply
    volumes.csv              ->  volumes.csv
    segmented/cut_planes.json ->  cutting_line.json   (reshaped, see below)

Two things the web expects that this pipeline does not produce:

  leg_no_cut.ply   The cut is made on the POINT CLOUD, before anything is
                   meshed, so an uncut limb mesh never exists. The cut mesh is
                   published under that name as well, which means the review
                   screen shows the cut already applied and moving the plane
                   does not re-cut anything. For a demo that is honest enough;
                   a run that cut the mesh instead would be a real change to
                   the pipeline, not a publishing detail.
  prep/framing.json
                   There is no framing stage, so there is no verdict to show.
                   The framing screen already handles its absence and says so.

The cutting planes are reshaped because the two sides name them differently.
This pipeline writes {space, case, planes[{label, centroid, normal}]}; the web
reads {markers[{centroid, normal, npts}]}. Only the wrapper changes — the
plane positions are copied through untouched.
"""
import argparse
import json
import os
import shutil

MESH_FILES = (("mesh/segmented_obj.ply", "leg_mesh.ply"),
              ("mesh/box.ply", "box_mesh.ply"),
              ("mesh/scene.ply", "scene_mesh.ply"))

# Published under this name too, for the reason in the module docstring.
UNCUT_SOURCE = "mesh/segmented_obj.ply"
UNCUT_PUBLISHED = "leg_no_cut.ply"


def copy_if_present(run_dir, relative_source, destination_dir, published_name):
    """Copy one file into the sample folder. Returns True when it was there."""
    source = os.path.join(run_dir, relative_source)
    if not os.path.exists(source):
        print(f"  missing  {relative_source}")
        return False
    shutil.copy2(source, os.path.join(destination_dir, published_name))
    size_mb = os.path.getsize(source) / (1024 * 1024)
    print(f"  copied   {relative_source:28s} -> {published_name}  ({size_mb:.1f} MB)")
    return True


def write_cutting_line(run_dir, destination_dir):
    """Rewrite this run's cutting planes in the shape the web reads."""
    source = os.path.join(run_dir, "segmented", "cut_planes.json")
    if not os.path.exists(source):
        print("  missing  segmented/cut_planes.json — the run made no cut")
        return False

    with open(source) as handle:
        recorded = json.load(handle)

    markers = []
    for plane in recorded.get("planes", []):
        markers.append({"centroid": plane["centroid"],
                        "normal": plane["normal"],
                        "npts": 0,
                        "source": "colour",
                        "label": plane.get("label", "")})

    if not markers:
        print("  missing  no planes inside cut_planes.json")
        return False

    destination = os.path.join(destination_dir, "cutting_line.json")
    with open(destination, "w") as handle:
        json.dump({"space": recorded.get("space", "levelled"),
                   "markers": markers}, handle, indent=2)
    print(f"  wrote    cutting_line.json ({len(markers)} plane(s))")
    return True


def publish(run_dir, samples_dir, sample_name):
    """Copy one run into web/public/samples/<sample_name>/."""
    destination_dir = os.path.join(samples_dir, sample_name)
    os.makedirs(destination_dir, exist_ok=True)
    print(f"\n{sample_name}:")

    complete = True
    for relative_source, published_name in MESH_FILES:
        if not copy_if_present(run_dir, relative_source, destination_dir,
                               published_name):
            complete = False

    if not copy_if_present(run_dir, UNCUT_SOURCE, destination_dir,
                           UNCUT_PUBLISHED):
        complete = False

    if not copy_if_present(run_dir, "volumes.csv", destination_dir,
                           "volumes.csv"):
        complete = False

    if not write_cutting_line(run_dir, destination_dir):
        complete = False

    if complete:
        print("  -> complete")
    else:
        print("  -> INCOMPLETE, the web app will not show this sample properly")
    return complete


def main():
    """Publish each run directory named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+",
                        help="run output directories to publish")
    parser.add_argument("--samples-dir", default="web/public/samples",
                        help="where the web app looks for its samples")
    parser.add_argument("--name", default=None,
                        help="sample name; defaults to the run folder's name")
    arguments = parser.parse_args()

    for run_dir in arguments.runs:
        run_dir = run_dir.rstrip("/")
        if arguments.name is not None and len(arguments.runs) == 1:
            sample_name = arguments.name
        else:
            sample_name = os.path.basename(run_dir)
        publish(run_dir, arguments.samples_dir, sample_name)


if __name__ == "__main__":
    main()
