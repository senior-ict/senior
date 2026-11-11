"""Stage 7 — Volume and circumference (leg-scan-measure), scaled by the reference cube.

Volume: signed tetrahedron sum V = sum a.(b x c) / 6 over Stage 6's watertight
meshes, in float64 (leg-scan-measure's server-side check). A mesh that is not
closed is still integrated but labelled `open (unreliable)`.

Scale (senior): the reference cube is the only object of known size, so
    k            = REFERENCE_REAL_SIZE_CM**3 / box_volume     cm3 per unit3
    linear_scale = k ** (1/3)                                 cm per unit

Circumference (leg-scan-measure): at each applied cutting plane, the plane is
intersected with the UNCUT limb surface (05_cut/mesh/leg_no_cut.ply), the
longest closed loop is taken, and
    tape    = convex hull perimeter in the plane (what a tape measure reads)
    contour = exact outline length
    area    = cross-section area

Outputs (07_measure/):
    volumes.csv        senior's column layout, so the web app reads it unchanged
    circumference.csv  one row per cutting plane
    measure.json       everything above in one file for the web app
"""
import csv
import json
import os

import numpy as np
import trimesh

from pipeline.config import REFERENCE_REAL_SIZE_CM
from pipeline.core.legscan import (circumference_on_plane, edge_stats, is_closed,
                                   signed_volume, surface_area)

# How far inside the cut the filled solid is sliced when the raw surface has a
# gap at the plane, in cm.
INSET_CM = 0.1

VOLUME_COLUMNS = ["name", "is_ref", "volume", "method", "ext_x", "ext_y", "ext_z",
                  "bbox_vol", "real_vol_cm3", "real_vol_L",
                  "size_x_cm", "size_y_cm", "size_z_cm"]


def _mesh_row(path, is_ref):
    """Raw measurements of one mesh in mesh units."""
    m = trimesh.load(path, force="mesh", process=False)
    m.merge_vertices()
    v, f = np.asarray(m.vertices, dtype=np.float64), np.asarray(m.faces, dtype=np.int64)
    closed = is_closed(f)
    ext = v.max(axis=0) - v.min(axis=0)
    return {
        "name": os.path.basename(path),
        "is_ref": is_ref,
        "volume": abs(signed_volume(v, f)),
        "method": "watertight" if closed else "open (unreliable)",
        "ext_x": float(ext[0]), "ext_y": float(ext[1]), "ext_z": float(ext[2]),
        "bbox_vol": float(np.prod(ext)),
        "area": surface_area(v, f),
        "edges": edge_stats(f),
    }


def measure_stage(fill_mesh_dir, uncut_limb_path, planes_path, output_dir):
    """Runs Stage 7. Returns the measure.json dict, or None if nothing could be scaled."""
    print()
    print("=" * 60)
    print(f"STAGE 7: Volume + circumference  (ref = {REFERENCE_REAL_SIZE_CM} cm cube)")
    print("=" * 60)
    os.makedirs(output_dir, exist_ok=True)
    for name in ("volumes.csv", "circumference.csv", "measure.json"):
        p = os.path.join(output_dir, name)
        if os.path.exists(p):
            os.remove(p)

    box_path = os.path.join(fill_mesh_dir, "box.ply")
    leg_path = os.path.join(fill_mesh_dir, "leg_cut.ply")
    if not os.path.exists(box_path):
        print("  No reference cube mesh — cannot scale. Aborting.")
        return None

    rows = [_mesh_row(box_path, True)]
    if os.path.exists(leg_path):
        rows.append(_mesh_row(leg_path, False))
    else:
        print("  No leg_cut.ply (cut deferred) — measuring the reference only")

    ref = rows[0]
    if ref["volume"] <= 0:
        print("  Reference cube has zero volume. Aborting.")
        return None
    k = REFERENCE_REAL_SIZE_CM ** 3 / ref["volume"]
    s = k ** (1.0 / 3.0)
    print(f"  ref mesh vol = {ref['volume']:.6f} unit3  ({ref['method']})")
    print(f"  k = {k:.6f} cm3/unit3   linear_scale = {s:.6f} cm/unit")
    for r in rows:
        r["real_vol_cm3"] = r["volume"] * k
        r["real_vol_L"] = r["real_vol_cm3"] / 1000.0
        r["size_x_cm"], r["size_y_cm"], r["size_z_cm"] = (r["ext_x"] * s, r["ext_y"] * s,
                                                          r["ext_z"] * s)
        print(f"  {r['name']:<14} {r['real_vol_cm3']:10.2f} cm3  "
              f"{r['size_x_cm']:.2f} x {r['size_y_cm']:.2f} x {r['size_z_cm']:.2f} cm  "
              f"[{r['method']}]")

    with open(os.path.join(output_dir, "volumes.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=VOLUME_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Circumference at each applied plane, on the uncut surface.
    circ = []
    planes = []
    if planes_path and os.path.exists(planes_path):
        with open(planes_path) as fh:
            planes = json.load(fh).get("planes", [])
    if planes and uncut_limb_path and os.path.exists(uncut_limb_path):
        m = trimesh.load(uncut_limb_path, force="mesh", process=False)
        m.merge_vertices()
        order = sorted(range(len(planes)), key=lambda i: planes[i]["centroid"][2])
        filled = None
        if os.path.exists(leg_path):
            filled = trimesh.load(leg_path, force="mesh", process=False)
            filled.merge_vertices()
        labels = ["bottom", "top"] if len(planes) == 2 else ["top"]
        for label, i in zip(labels, order):
            p = planes[i]
            c = circumference_on_plane(m.vertices, m.faces, p["normal"], p["centroid"])
            source = "surface"
            if (c is None or not c["closed"]) and filled is not None:
                # The raw surface has a hole where the plane crosses it. The
                # filled solid does not, so slice it INSET_CM inside the cut
                # (toward the kept side) -- on the plane itself it is the flat
                # cap and the slice would be degenerate.
                nrm = np.asarray(p["normal"], dtype=np.float64)
                inward = nrm if label == "bottom" else -nrm
                q = np.asarray(p["centroid"], dtype=np.float64) + inward * (INSET_CM / s)
                c2 = circumference_on_plane(filled.vertices, filled.faces, nrm, q)
                if c2 is not None and c2["closed"]:
                    c = c2
                    source = f"filled solid, {INSET_CM * 10:.0f} mm inside the cut"
            nz = abs(float(np.asarray(p["normal"])[2]))
            entry = {"plane": label, "source": source,
                     "centroid": p["centroid"], "normal": p["normal"],
                     "tilt_deg": float(np.degrees(np.arccos(min(1.0, nz))))}
            if c is None:
                entry.update(tape_cm=None, contour_cm=None, area_cm2=None, closed=False)
                print(f"  {label} cut: plane misses the limb")
            else:
                entry.update(tape_cm=c["tape"] * s, contour_cm=c["contour"] * s,
                             area_cm2=(c["area"] * s * s) if np.isfinite(c["area"]) else None,
                             closed=c["closed"], loops=c["loop_count"],
                             hull=c["hull"].tolist())
                gap = ("" if c["closed"] else "  (gap in scan)") + (
                    "" if source == "surface" else f"  [{source}]")
                print(f"  {label} cut: circumference {entry['tape_cm']:.2f} cm "
                      f"(outline {entry['contour_cm']:.2f} cm), tilt "
                      f"{entry['tilt_deg']:.1f} deg{gap}")
            circ.append(entry)
        with open(os.path.join(output_dir, "circumference.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["plane", "tape_cm", "contour_cm", "area_cm2", "tilt_deg", "closed"])
            for e in circ:
                w.writerow([e["plane"], e["tape_cm"], e["contour_cm"], e["area_cm2"],
                            e["tilt_deg"], e["closed"]])

    leg = next((r for r in rows if not r["is_ref"]), None)
    result = {
        "reference_cm": REFERENCE_REAL_SIZE_CM,
        "cm_per_unit": s,
        "reference": {k2: ref[k2] for k2 in ("name", "volume", "method", "edges")},
        "leg": None if leg is None else {
            "name": leg["name"],
            "volume_ml": leg["real_vol_cm3"],
            "watertight": leg["method"] == "watertight",
            "edges": leg["edges"],
            "area_cm2": leg["area"] * s * s,
            "size_cm": [leg["size_x_cm"], leg["size_y_cm"], leg["size_z_cm"]],
        },
        "circumference": circ,
    }
    with open(os.path.join(output_dir, "measure.json"), "w") as fh:
        json.dump(result, fh, indent=2)
    return result
