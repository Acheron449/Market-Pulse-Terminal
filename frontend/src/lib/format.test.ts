import { describe, expect, it } from "vitest";

import {
  EM_DASH,
  ageSeconds,
  arrowFor,
  formatPercent,
  formatPrice,
  formatSigned,
  formatTime,
  formatVolume,
  normalise,
  toneFor,
  truncate,
} from "./format";

describe("formatPrice", () => {
  it("uses two decimals and thousands separators", () => {
    expect(formatPrice(7475.456)).toBe("7,475.46");
    expect(formatPrice(0.5)).toBe("0.50");
  });

  it("returns an em dash for invalid input", () => {
    expect(formatPrice(Number.NaN)).toBe(EM_DASH);
    expect(formatPrice(Number.POSITIVE_INFINITY)).toBe(EM_DASH);
    expect(formatPrice(undefined)).toBe(EM_DASH);
  });
});

describe("signs", () => {
  it("signs changes explicitly", () => {
    expect(formatSigned(1.2)).toBe("+1.20");
    expect(formatSigned(-25.125)).toBe("-25.13");
    expect(formatPercent(0.35)).toBe("+0.35%");
  });
});

describe("formatVolume", () => {
  it("uses K, M and B", () => {
    expect(formatVolume(950)).toBe("950");
    expect(formatVolume(12_345)).toBe("12.3K");
    expect(formatVolume(123_456_789)).toBe("123.46M");
    expect(formatVolume(2_500_000_000)).toBe("2.50B");
  });

  it("guards invalid values", () => {
    expect(formatVolume(-1)).toBe(EM_DASH);
    expect(formatVolume(null)).toBe(EM_DASH);
  });
});

describe("toneFor", () => {
  it("is green for a rise", () => {
    expect(toneFor(1.2)).toBe("up");
    expect(toneFor(-1.2)).toBe("down");
    expect(toneFor(0)).toBe("flat");
  });

  it("inverts the VIX", () => {
    expect(toneFor(3.08, true)).toBe("down");
    expect(toneFor(-3.08, true)).toBe("up");
  });
});

describe("arrowFor", () => {
  it("always carries a direction, so colour is not the only cue", () => {
    expect(arrowFor(1)).toBe("▲");
    expect(arrowFor(-1)).toBe("▼");
    expect(arrowFor(0)).toBe("→");
    expect(arrowFor(undefined)).toBe("→");
  });
});

describe("time helpers", () => {
  it("formats a timestamp and reports its age", () => {
    expect(formatTime("2026-11-06T21:05:00Z")).not.toBe(EM_DASH);
    expect(formatTime("not-a-date")).toBe(EM_DASH);
    const now = new Date("2026-11-06T21:06:00Z").getTime();
    expect(ageSeconds("2026-11-06T21:05:00Z", now)).toBe(60);
    expect(ageSeconds(null)).toBeNull();
  });
});

describe("truncate and normalise", () => {
  it("truncates long names", () => {
    expect(truncate("Advanced Micro Devices", 12)).toBe("Advanced Mi…");
    expect(truncate("NVIDIA", 12)).toBe("NVIDIA");
  });

  it("normalises a series to 0..1", () => {
    expect(normalise([10, 20, 30])).toEqual([0, 0.5, 1]);
    expect(normalise([5, 5, 5])).toEqual([0.5, 0.5, 0.5]);
    expect(normalise([])).toEqual([]);
  });
});
