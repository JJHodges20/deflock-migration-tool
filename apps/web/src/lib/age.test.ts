import { describeAge } from "./age";

describe("describeAge", () => {
  const now = new Date("2026-10-19T18:00:00Z");

  it("words the age and flags staleness against the configured threshold", () => {
    expect(describeAge("2026-10-19T17:30:00Z", now, 48)).toEqual({ text: "under 1 h old", hours: 0.5, stale: false });
    expect(describeAge("2026-10-19T13:00:00Z", now, 48).text).toBe("5 h old");
    expect(describeAge("2026-10-16T18:00:00Z", now, 48)).toMatchObject({ text: "3 days old", stale: true });
    expect(describeAge("2026-10-17T19:00:00Z", now, 48)).toMatchObject({ text: "47 h old", stale: false });
  });

  it("never claims an age it does not know", () => {
    expect(describeAge(null, now, 48)).toEqual({ text: "age unknown", hours: null, stale: false });
    expect(describeAge("not a date", now)).toEqual({ text: "age unknown", hours: null, stale: false });
    expect(describeAge("2026-10-19T19:00:00Z", now).hours).toBe(0); // a future timestamp is clamped, not negative
  });
});
