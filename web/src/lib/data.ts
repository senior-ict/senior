import type { CutPlane, SampleDataset, VolumeRow } from "./types";

/** Precomputed runs shipped with the site. These work with no backend at all;
 *  only new uploads need the GPU service.
 *
 *  Both were produced by this pipeline, branch old-pipeline at 537e216. The
 *  cut lands on the MIDDLE of each painted band, which is where this pipeline
 *  places its cutting planes. Each run has a truth measured on the same leg
 *  with a tape, between the two band edges, and the result screen quotes the
 *  error against it.
 *
 *  A third capture, 5_circumference_calculation_2c_hairless, is deliberately not shipped: on it
 *  the reference test scored the LEG above the cube, so the run scaled from
 *  the wrong object and produced no usable measurement. It is a real failure
 *  of this pipeline, not a bad capture, and it is written up in the report
 *  rather than shown here as if it were a result.
 *
 *  The review screen cannot move the cut on these samples. This pipeline cuts
 *  the point cloud before anything is meshed, so no uncut limb mesh exists to
 *  re-cut; leg_no_cut.ply is the already-cut mesh. */
export const SAMPLES: SampleDataset[] = [
  {
    id: "5_circumference_calculation_1k",
    label: "Lower leg \u2014 subject K",
    subject: "Human lower leg between two green bands",
    nominalMl: null,
    truth: {
      volumeMl: 1420.21,
      method: "tape profile, truncated cones",
      note: "Measured between the two bands with a tape, then summed as truncated cones.",
    },
    frames: 8,
    meshes: {
      leg: "/samples/5_circumference_calculation_1k/leg_mesh.ply",
      box: "/samples/5_circumference_calculation_1k/box_mesh.ply",
      scene: "/samples/5_circumference_calculation_1k/scene_mesh.ply",
      legNoCut: "/samples/5_circumference_calculation_1k/leg_no_cut.ply",
    },
    volumesCsv: "/samples/5_circumference_calculation_1k/volumes.csv",
    cuttingLine: "/samples/5_circumference_calculation_1k/cutting_line.json",
  },
  {
    id: "5_circumference_calculation_3s_hairless",
    label: "Lower leg \u2014 subject S",
    subject: "Human lower leg, shaved before the capture",
    nominalMl: null,
    truth: {
      volumeMl: 1847.06,
      method: "tape profile, truncated cones",
      note: "The leg was shaved and re-measured so the tape and the cameras read the same surface.",
    },
    frames: 7,
    meshes: {
      leg: "/samples/5_circumference_calculation_3s_hairless/leg_mesh.ply",
      box: "/samples/5_circumference_calculation_3s_hairless/box_mesh.ply",
      scene: "/samples/5_circumference_calculation_3s_hairless/scene_mesh.ply",
      legNoCut: "/samples/5_circumference_calculation_3s_hairless/leg_no_cut.ply",
    },
    volumesCsv: "/samples/5_circumference_calculation_3s_hairless/volumes.csv",
    cuttingLine: "/samples/5_circumference_calculation_3s_hairless/cutting_line.json",
  },
];

/** Stage list for the processing screen. Times measured on an RTX 4060,
 *  6 photos. Do not inflate these.
 *
 * The pipeline runs in two passes with the user in between, so the same stage
 * numbers mean different things either side of the review. Naming them by what
 * they produce in THAT pass is the only honest labelling: on the first pass
 * stages 4-6 build the limb's solid and measure the reference cube, but do not
 * measure the limb: its extent is not known until the cut is confirmed. */
export const MEASURE_STAGES = [
  { n: 1, label: "VGGT inference", out: "predictions.npz", seconds: 180 },
  { n: 2, label: "Point cloud export", out: "points.ply", seconds: 3 },
  { n: 3, label: "Level, split the objects, cut at the bands", out: "segmented_obj.ply", seconds: 20 },
  { n: 4, label: "Poisson reconstruction", out: "segmented_obj_recon.ply", seconds: 20 },
  { n: 5, label: "Close the mesh", out: "segmented_obj.ply", seconds: 10 },
  { n: 6, label: "Scale from the cube, measure", out: "volumes.csv", seconds: 3 },
] as const;

/** The second pass: the cut the user confirmed, then the object itself. Only
 *  stages 5 and 6 appear. The cut is a plane slice through the watertight solid
 *  Stage 5 already built, so neither the segmentation nor the surface
 *  reconstruction is repeated — an edit costs seconds. */
export const CUT_STAGES = [
  { n: 5, label: "Apply the confirmed cut", out: "leg_cut.ply", seconds: 3 },
  { n: 6, label: "Volume by surface integration", out: "volumes.csv", seconds: 2 },
] as const;

export const STAGES = MEASURE_STAGES;

/** Minimal CSV parse — volumes.csv has no quoted fields. */
export function parseVolumesCsv(text: string): VolumeRow[] {
  const [header, ...lines] = text.trim().split("\n");
  const cols = header.split(",");
  return lines
    .filter((l) => l.trim())
    .map((line) => {
      const cells = line.split(",");
      // True when the CSV carries this column.
      const has = (k: string) => cols.indexOf(k) >= 0;
      // Raw cell text for this column on the current row.
      const get = (k: string) => cells[cols.indexOf(k)];
      // Cell parsed as a number, falling back to 0 when it is not finite.
      const num = (k: string) => {
        const v = parseFloat(get(k));
        return Number.isFinite(v) ? v : 0;
      };
      // Two Stage 6 implementations are in circulation and they name these
      // differently. The parked one reports an ORIENTED box (obb_*/height_cm),
      // main's reports an AXIS-ALIGNED one (ext_*/size_*_cm). Normalise to one
      // shape here so nothing downstream has to know, but remember which was
      // read — the two are not interchangeable for deriving scale, since an
      // AABB around a tilted cube measures its diagonal.
      const aabb = !has("obb_b");
      return {
        name: get("name"),
        is_ref: get("is_ref") === "True",
        volume: num("volume"),
        method: get("method"),
        // obb_a is the vertical axis; main's vertical is ext_z, the scene
        // having been levelled so Z is up.
        obb_a: aabb ? num("ext_z") : num("obb_a"),
        obb_b: aabb ? num("ext_x") : num("obb_b"),
        obb_c: aabb ? num("ext_y") : num("obb_c"),
        aabb,
        voxel: has("voxel") && get("voxel") ? num("voxel") : null,
        real_vol_cm3: num("real_vol_cm3"),
        real_vol_L: num("real_vol_L"),
        height_cm: aabb ? num("size_z_cm") : num("height_cm"),
        width_cm: aabb ? num("size_x_cm") : num("width_cm"),
        depth_cm: aabb ? num("size_y_cm") : num("depth_cm"),
      } satisfies VolumeRow;
    });
}

// Fetches and parses a run's volumes.csv.
export async function loadVolumes(url: string): Promise<VolumeRow[]> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`volumes.csv ${res.status}`);
  return parseVolumesCsv(await res.text());
}

/** The reference cube's edge in centimetres. The shipped runs all use the
 *  10 cm ArUco cube; the 14 cm block it replaced is no longer in any sample. */
export const REFERENCE_CM = 10.0;

/** cm per mesh unit — derived the way the Stage 6 that produced this CSV did it.
 *
 * Mirroring matters more than picking the better method. If the viewer scaled
 * geometry differently from the stage that computed the volumes, an object would
 * appear at a size that contradicts its own printed measurement, and there would
 * be no way to tell which was wrong.
 *
 * Returns null when no scale can be derived, so the caller can say so. It used
 * to return `14 / 0` here and hand Infinity to the loader, which multiplied every
 * vertex by it and produced a scene of NaNs — a blank viewport with no error,
 * indistinguishable from a browser that cannot draw at all.
 */
export function linearScale(rows: VolumeRow[]): number | null {
  const ref = rows.find((r) => r.is_ref);
  if (!ref) return null;

  // Preferred: the reference's measured EDGE, horizontals only. obb_a is the
  // vertical axis, which the floor truncates — averaging it in drags the
  // estimate small and inflates everything measured against it.
  let scale = REFERENCE_CM / ((ref.obb_b + ref.obb_c) / 2);

  if (ref.aabb) {
    // main's Stage 6. Its extents are axis-aligned, so on a tilted cube they
    // read the diagonal — using them here gives 44.0 cm/unit against a true
    // 59.8, a 26% error. Its own derivation is the volume ratio, so use that
    // instead and stay consistent with the numbers it printed. The cube root
    // treats V^(1/3) as an edge length, which only holds for a perfect cube:
    // measured +2% against the fitted-face answer on inputs/0_first_sample_3.
    scale = Math.cbrt(ref.real_vol_cm3 / ref.volume);
  }
  return Number.isFinite(scale) && scale > 0 ? scale : null;
}

let planeSeq = 0;
// Returns a fresh unique id for a newly added plane.
export function newPlaneId() {
  return `p${++planeSeq}`;
}

// Fetches the detected cutting planes, returning an empty list when there are none yet.
export async function loadCutPlanes(url: string): Promise<CutPlane[]> {
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const json = await res.json();
    // Lowest first in both lists, so the two can be paired end to end.
    const byHeight = (a: any, b: any) => a.centroid[2] - b.centroid[2];
    const candidates = (json.candidates ?? []).slice().sort(byHeight);
    const markers = (json.markers ?? []).slice().sort(byHeight);

    // "candidates" is every band detection, at the CENTRE of its painted
    // stripe. "markers" is what the run would actually cut on: since 5ab597f
    // Stage 3 slides each plane from the stripe's centre to its INNER edge,
    // which is the span a tape measures and is worth 15-35% of the volume.
    //
    // Showing the reviewer the candidates would quietly undo that — they would
    // confirm the centres, those would come back as override_planes, and the
    // cut would land where it used to. So the markers are what is shown, with
    // the candidate they came from kept as each plane's `origin`, which is the
    // "marker detected at …" row and its reset button on the review screen.
    const paired =
      markers.length > 0 && candidates.length === markers.length;

    // Falls back to whichever list exists when they cannot be paired — an
    // older file with only "markers", or a run where --cut-mode trimmed the
    // markers to one and the reviewer still needs to see both bands.
    const raw = paired
      ? markers
      : candidates.length
        ? candidates
        : markers;

    return raw.map((m: any, index: number) => {
      const detected = paired ? candidates[index] : m;
      return {
        id: newPlaneId(),
        centroid: m.centroid as [number, number, number],
        normal: m.normal as [number, number, number],
        npts: m.npts ?? 0,
        source: "detected" as const,
        origin: {
          centroid: detected.centroid as [number, number, number],
          normal: detected.normal as [number, number, number],
        },
      };
    });
  } catch {
    return [];
  }
}
