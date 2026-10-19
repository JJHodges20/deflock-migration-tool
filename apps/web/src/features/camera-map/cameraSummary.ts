import type { CameraFeatureProperties } from "@/lib/api/types";
import type { Feature, Point } from "geojson";

export interface CameraSummary {
  total: number;
  flock: number;
  otherKnown: number;
  unknown: number;
  uncertain: number;
  outsideEnvelope: number;
}

export const emptySummary: CameraSummary = { total: 0, flock: 0, otherKnown: 0, unknown: 0, uncertain: 0, outsideEnvelope: 0 };

/** Counts of mapped records in the current view. These describe records, never physical devices. */
export function summarizeCameraFeatures(features: Feature<Point, CameraFeatureProperties>[]): CameraSummary {
  const summary = { ...emptySummary };
  for (const feature of features) {
    const p = feature.properties;
    summary.total += 1;
    if (p.uncertain) summary.uncertain += 1;
    if (!p.in_envelope) summary.outsideEnvelope += 1;
    if (p.is_flock) summary.flock += 1;
    else if (p.manufacturer) summary.otherKnown += 1;
    else summary.unknown += 1;
  }
  return summary;
}
