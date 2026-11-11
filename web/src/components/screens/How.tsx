"use client";

import { Label, Panel } from "@/components/ui/primitives";
import { CUT_STAGES, MEASURE_STAGES } from "@/lib/data";

const STAGES = [...MEASURE_STAGES.filter((s) => s.n < 5), ...CUT_STAGES];

const DETAIL: Record<number, string> = {
  1: "One forward pass of VGGT-1B produces a 3D point and a confidence value for every pixel of every photo, plus camera poses. This is the only neural step and where all the uncertainty originates.",
  2: "Points are filtered by confidence — about 55% survive — and statistical outliers removed. The result is one coloured cloud of the whole scene: floor, object, cube.",
  3: "The floor plane is removed (without it everything is connected through the ground and cannot be separated), the rest is clustered into objects, and the reference cube is identified by how cube-like and how black-and-white it is. The duplicated surface VGGT emits is collapsed and the survivors projected onto a locally fitted quadratic surface. The marker band is found using the colour Stage 0 measured from your own photographs rather than a fixed threshold, and a plane is fitted through it. Each band is a painted stripe about 2 cm wide, so that plane lands in the stripe's middle and is then slid to its INNER edge, which is the span a tape measures between the two bands — the difference is worth 15-35% of the volume. The reference cube's points are mended in the same stage: anything more than 1 mm off its nearest face is moved onto it, and each face is gridded at 4 mm so that an empty cell gets a point. You confirm the planes before anything is cut.",
  4: "The point cloud becomes a triangle mesh by Poisson reconstruction, which follows the points closely. Poisson carries no guarantee that the result is a single solid, so if the repair stage cannot bring the mesh to Euler characteristic 2, this stage runs again with an alpha shape — whose search selects on that property and therefore cannot fail it.",
  5: "leg-scan-measure's exact plane cut, applied to Stage 4's surface. Every triangle the plane crosses is split along it, and the new vertex on each crossed edge is shared by both neighbouring triangles, so the cut leaves one clean boundary loop. One plane keeps what is below it; two keep what lies between them. If the cut leaves several pieces, only the largest is kept.",
  6: "PyMeshFix closes the open cut ends — and any holes the reconstruction left — into a single watertight solid, keeping only the main piece. The reference cube is closed the same way. The result is checked edge by edge: every edge must be shared by exactly two triangles.",
  7: "A closed mesh has an exact volume: sum the signed tetrahedron volumes a·(b×c)/6 over its triangles, in double precision. Real-world size comes from the reference cube — the ratio of its true 1000 cm³, a 10 cm edge, to its measured mesh volume. The circumference at each cut is where the plane meets the uncut surface: the longest closed loop, measured as its convex hull perimeter — what a tape measure reads.",
};

// Static help screen explaining how to photograph an object.
export function How() {
  return (
    <div className="fadein" style={{ display: "grid", gap: 16, maxWidth: 760 }}>
      <h2 style={{ font: "500 22px/1.2 var(--sans)", margin: 0 }}>
        How it works
      </h2>
      <p
        style={{
          font: "400 14px/1.65 var(--sans)",
          color: "var(--muted)",
          margin: 0,
        }}
      >
        A framing gate reads your photographs first, then seven stages run. Only
        the first of them uses a neural network; everything after is geometry.
      </p>

      {STAGES.map((s) => (
        <Panel key={s.n}>
          <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
            <span
              style={{
                font: "500 12px/1 var(--mono)",
                color: "var(--accent)",
              }}
            >
              {s.n}
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ font: "500 14px/1.3 var(--sans)" }}>{s.label}</div>
              <p
                style={{
                  font: "400 13px/1.65 var(--sans)",
                  color: "var(--muted)",
                  margin: "7px 0 0",
                }}
              >
                {DETAIL[s.n]}
              </p>
            </div>
          </div>
        </Panel>
      ))}

      <Panel>
        <Label>What this cannot yet do</Label>
        <p
          style={{
            font: "400 13px/1.7 var(--sans)",
            color: "var(--muted)",
            margin: "10px 0 0",
          }}
        >
          Scale cannot be validated. With only one object of known size, the cube
          defines the scale — so it can never disagree with itself. Confirming
          accuracy needs a second known object: calibrate on the cube, predict the
          second object&apos;s size, and compare against a caliper measurement.
          That measurement does not exist yet.
        </p>
      </Panel>
    </div>
  );
}
