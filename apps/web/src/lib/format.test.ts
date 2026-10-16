import { clampBbox, formatDistance, formatDuration, formatSignedDuration } from "./format";

describe("format helpers", () => {
  it("formats durations in minutes and hours", () => {
    expect(formatDuration(89)).toBe("1 min");
    expect(formatDuration(730.7)).toBe("12 min");
    expect(formatDuration(3600)).toBe("1 h");
    expect(formatDuration(3900)).toBe("1 h 5 min");
  });

  it("formats distances", () => {
    expect(formatDistance(850)).toBe("850 m");
    expect(formatDistance(6373)).toBe("6.4 km");
    expect(formatDistance(40308)).toBe("40 km");
  });

  it("formats signed extra time without claiming savings under 30 s", () => {
    expect(formatSignedDuration(0)).toBe("no extra time");
    expect(formatSignedDuration(600)).toBe("+10 min");
    expect(formatSignedDuration(-120)).toBe("−2 min");
  });

  it("clamps oversized bounding boxes around their centre", () => {
    const [w, s, e, n] = clampBbox([-106, 39, -104, 41], 0.6);
    expect(e - w).toBeLessThanOrEqual(0.6);
    expect(n - s).toBeLessThanOrEqual(0.6);
    expect((w + e) / 2).toBeCloseTo(-105, 5);
    expect((s + n) / 2).toBeCloseTo(40, 5);
    expect(clampBbox([-105.1, 39.7, -105.0, 39.8], 0.6)).toEqual([-105.1, 39.7, -105.0, 39.8]);
  });
});
