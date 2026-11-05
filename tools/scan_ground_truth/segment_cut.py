"""Cut a mesh to the segment lying between two planes, and cap the two faces.

This mirrors what `pipeline/core/meshcut.py` does to a reconstruction, kept as
its own copy on purpose. The ground truth has to be measurable from any branch,
including the older pipelines that predate that module, and a reference that
only reproduces on one branch is not much of a reference.

The two implementations agree by construction: both take a capped plane slice
per marker and keep what lies between them. Verified on 6_3d_scanner_2k, where
both routes return 1566.8 cm3.
"""

import numpy as np

MIN_FACES_AFTER_CUT = 50


def cut_between_planes(mesh, planes):
    """Keep only the part of a mesh lying between two planes, capping each cut.

    Each plane is a dict with a "centroid" and a "normal". The normals are
    expected to point at each other, so the wanted segment is on the positive
    side of both, and the cord each plane sits on falls outside it.

    Returns (cut_mesh, case_label). The mesh comes back uncut, with a label
    saying why, whenever the cut would leave almost nothing behind.
    """
    if len(planes) != 2:
        return mesh, "need_exactly_two_planes"

    cut = mesh
    for plane in planes:
        origin = np.asarray(plane["centroid"], dtype=np.float64)
        normal = np.asarray(plane["normal"], dtype=np.float64)
        normal = normal / (np.linalg.norm(normal) + 1e-8)
        cut = cut.slice_plane(plane_origin=origin, plane_normal=normal,
                              cap=True)
        if cut is None or len(cut.faces) == 0:
            return mesh, "cut_removed_everything"
        cut.merge_vertices()

    if len(cut.faces) < MIN_FACES_AFTER_CUT:
        return mesh, "too_few_after_cut"
    return cut, "case_2_between"
