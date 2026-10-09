import { describe, expect, it } from "vitest";
import { businessDate } from "../src/utils/date";

describe("Shanghai business dates", () => {
  it("uses the next calendar day at Shanghai midnight", () => {
    expect(businessDate(new Date("2026-10-07T15:59:59Z"))).toBe("2026-10-07");
    expect(businessDate(new Date("2026-10-07T16:00:00Z"))).toBe("2026-10-08");
  });
  it("keeps booking date offsets correct across a year boundary", () => {
    const now = Date.parse("2026-12-31T16:15:00Z");
    expect([0, 1, 2].map(day => businessDate(now + day * 86400000)))
      .toEqual(["2027-01-01", "2027-01-02", "2027-01-03"]);
  });
});
