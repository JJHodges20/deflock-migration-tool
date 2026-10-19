import type { CameraFeatureProperties } from "@/lib/api/types";
import type { Feature, Point } from "geojson";
import { summarizeCameraFeatures } from "./cameraSummary";

function feature(overrides: Partial<CameraFeatureProperties>): Feature<Point, CameraFeatureProperties> {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [-104.95, 39.75] },
    properties: {
      source_key: "osm:node:1",
      source_version: 1,
      source_timestamp: null,
      manufacturer: null,
      is_flock: false,
      operator: null,
      direction_raw: null,
      camera_direction_raw: null,
      direction_conflict: false,
      lifecycle_state: "mapped",
      lifecycle_evidence: null,
      uncertain: false,
      check_date: null,
      geometry_quality: "point",
      in_envelope: true,
      missing_since: null,
      source_url: "https://www.openstreetmap.org/node/1",
      ...overrides,
    },
  };
}

describe("summarizeCameraFeatures", () => {
  it("counts records by manufacturer scope, uncertainty, and envelope", () => {
    const summary = summarizeCameraFeatures([
      feature({ is_flock: true, manufacturer: "flock_safety" }),
      feature({ manufacturer: "axon" }),
      feature({}),
      feature({ is_flock: true, manufacturer: "flock_safety", uncertain: true, lifecycle_state: "no_longer_mapped" }),
      feature({ manufacturer: "axon", in_envelope: false }),
    ]);
    expect(summary).toEqual({ total: 5, flock: 2, otherKnown: 2, unknown: 1, uncertain: 1, outsideEnvelope: 1 });
  });

  it("returns zeros for an empty view", () => {
    expect(summarizeCameraFeatures([]).total).toBe(0);
  });
});
