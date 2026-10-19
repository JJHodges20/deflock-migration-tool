/** Client-side GeoJSON export of one planned option (roadmap section 11). Nothing is uploaded or stored. */

import type { PlanResponse, RouteOptionOut } from "./api/types";

export const EXPORT_WARNING =
  "Another navigation application may recalculate a different path from this geometry; the file carries no camera avoidance. Camera counts describe mapped OpenStreetMap records at the snapshot date, not physical devices.";

export interface ExportContext {
  originLabel: string;
  destinationLabel: string;
  generatedAt: Date;
  disclaimer: string;
  regionId: string;
  searchStatus: string;
}

export function routeToGeoJSON(option: RouteOptionOut, result: PlanResponse, context: ExportContext) {
  const assessment = option.assessment;
  return {
    type: "FeatureCollection" as const,
    features: [
      {
        type: "Feature" as const,
        geometry: option.geometry,
        properties: {
          application: "DeFlockMigration",
          region_id: context.regionId,
          generated_at: context.generatedAt.toISOString(),
          origin_label: context.originLabel,
          destination_label: context.destinationLabel,
          profiles: option.profiles,
          estimated_duration_seconds: option.estimated_duration_seconds,
          length_meters: option.length_meters,
          extra_duration_seconds: option.extra_duration_seconds,
          matched_camera_record_count: option.matched_camera_record_count,
          uncertain_nearby_camera_count: option.uncertain_nearby_camera_count,
          exposure_count: option.exposure_count,
          assessment_coverage_status: option.assessment_coverage_status,
          counting_method_version: option.counting_method_version,
          camera_scope: option.camera_scope,
          camera_snapshot_id: option.camera_snapshot_id,
          camera_source_as_of: option.camera_source_as_of,
          camera_downloaded_at: option.camera_downloaded_at,
          road_graph_version: option.road_graph_version,
          search_status: context.searchStatus,
          search_method_version: result.search.method_version,
          generated_by: option.generated_by,
          maneuvers: option.maneuvers.map((m) => ({ instruction: m.instruction, street_names: m.street_names, length_meters: m.length_meters, time_seconds: m.time_seconds, begin_shape_index: m.begin_shape_index, end_shape_index: m.end_shape_index })),
          encounters: assessment ? assessment.encounters.filter((e) => e.status !== "excluded_scope").map((e) => ({ source_key: e.source_key, status: e.status, distance_m: e.distance_m, position_m: e.position_m, source_url: e.source_url })) : null,
          warning: EXPORT_WARNING,
          disclaimer: context.disclaimer,
        },
      },
    ],
  };
}

export function exportFileName(option: RouteOptionOut, generatedAt: Date): string {
  const stamp = generatedAt.toISOString().replace(/[-:]/g, "").slice(0, 15);
  return `deflockmigration-${option.profiles.join("-")}-${stamp}.geojson`;
}

/** Trigger a browser download of a JSON document. Returns false when the DOM APIs are unavailable. */
export function downloadJSON(name: string, document_: unknown): boolean {
  if (typeof window === "undefined" || typeof URL.createObjectURL !== "function") return false;
  const blob = new Blob([JSON.stringify(document_, null, 2)], { type: "application/geo+json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}
