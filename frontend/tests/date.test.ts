import { describe, expect, it } from "vitest";
import { businessDate, futureActivityStart } from "../src/utils/date";

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

it("requires a strictly future activity start in Shanghai time",()=>{
 const now=Date.parse("2026-10-15T11:00:00Z");
 expect(futureActivityStart("2026-10-09","19:00",now)).toBe(false);
 expect(futureActivityStart("2026-10-15","19:00",now)).toBe(false);
 expect(futureActivityStart("2026-10-15","19:01",now)).toBe(true);
 expect(futureActivityStart("2026-10-16","00:00",now)).toBe(true);
 expect(futureActivityStart("invalid","19:00",now)).toBe(false);
});
