export type Units = "km" | "mi";

const METERS_PER_MILE = 1609.344;
const FEET_PER_METER = 3.28084;

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** All server values are meters; conversion happens here and only here. */
export function formatDistance(meters: number, units: Units = "km"): string {
  if (units === "mi") {
    const miles = meters / METERS_PER_MILE;
    if (miles < 0.1) return `${Math.round(meters * FEET_PER_METER)} ft`;
    return `${miles.toFixed(miles < 10 ? 1 : 0)} mi`;
  }
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(meters < 10000 ? 1 : 0)} km`;
}

export function formatSignedDuration(seconds: number): string {
  if (Math.abs(seconds) < 30) return "no extra time";
  const sign = seconds > 0 ? "+" : "−";
  return `${sign}${formatDuration(Math.abs(seconds))}`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** Clamp a bounding box so a viewport query never exceeds the server's size limit. */
export function clampBbox(bbox: [number, number, number, number], maxDegrees: number): [number, number, number, number] {
  const [west, south, east, north] = bbox;
  const cx = (west + east) / 2;
  const cy = (south + north) / 2;
  const halfW = Math.min((east - west) / 2, maxDegrees / 2 - 0.0001);
  const halfH = Math.min((north - south) / 2, maxDegrees / 2 - 0.0001);
  return [cx - halfW, cy - halfH, cx + halfW, cy + halfH];
}
