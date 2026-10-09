import { describe, expect, it } from "vitest";
import { activityPollDelay, tournamentPollDelay } from "../src/domain/activity-polling";

describe("activity refresh cadence", () => {
  it("stops terminal tournaments even if unfinished matches remain", () => {
    for (const status of ["finished", "cancelled", "closed", "draft"])
      expect(tournamentPollDelay({ status, matches: [{ key: "1", group_no: 1, round_no: 1, position: 1, kind: "knockout", status: "pending", team_a_id: 1, team_b_id: 2 }] })).toBeNull();
  });
  it("refreshes playable matches faster than registration or unresolved brackets", () => {
    const match = { key: "1", group_no: 1, round_no: 1, position: 1, kind: "knockout", status: "pending", team_a_id: 1, team_b_id: 2 };
    expect(tournamentPollDelay({ status: "ongoing", matches: [match] })).toBe(10_000);
    expect(tournamentPollDelay({ status: "open", matches: [{ ...match, team_b_id: null }] })).toBe(20_000);
    expect(tournamentPollDelay({ status: "ongoing", matches: [{ ...match, status: "finished" }] })).toBe(20_000);
    expect(tournamentPollDelay(null)).toBe(20_000);
  });
  it("keeps review, waitlist, payment and ongoing activity responsive", () => {
    for (const registration of [{ approval: "pending" }, { admission: "review" }, { admission: "waitlisted" }, { payment: "pending" }, { payment: "unverified" }, { payment: "abnormal" }])
      expect(activityPollDelay([{ kind: "tournament", phase: "open", status: "open", registration }])).toBe(15_000);
    expect(activityPollDelay([{ kind: "post", status: "open", registration: { status: "pending" } }])).toBe(15_000);
    expect(activityPollDelay([{ phase: "ongoing" }])).toBe(15_000);
  });
  it("does not accelerate for expired, rejected, closed or historical registrations", () => {
    expect(activityPollDelay([])).toBe(45_000);
    for (const item of [
      { status: "closed", registration: { payment: "pending" } },
      { phase: "ended", registration: { approval: "pending" } },
      { registration: { admission: "expired", payment: "pending" } },
      { registration: { approval: "rejected", payment: "pending" } },
      { registration: { approval: "approved", admission: "active", payment: "paid" } },
    ]) expect(activityPollDelay([item])).toBe(45_000);
  });
});
