/** Data-age wording for badges. Pure: the caller supplies "now" so tests and prints are deterministic. */

export interface AgeBadge {
  text: string; // e.g. "5 h old", "3 days old", "age unknown"
  hours: number | null;
  stale: boolean; // older than the configured threshold, when one is given
}

export function describeAge(iso: string | null | undefined, now: Date, staleAfterHours?: number | null): AgeBadge {
  if (!iso) return { text: "age unknown", hours: null, stale: false };
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return { text: "age unknown", hours: null, stale: false };
  const hours = Math.max(0, (now.getTime() - then.getTime()) / 3_600_000);
  const stale = staleAfterHours !== undefined && staleAfterHours !== null && hours > staleAfterHours;
  let text: string;
  if (hours < 1) text = "under 1 h old";
  else if (hours < 48) text = `${Math.round(hours)} h old`;
  else text = `${Math.round(hours / 24)} days old`;
  return { text, hours, stale };
}
