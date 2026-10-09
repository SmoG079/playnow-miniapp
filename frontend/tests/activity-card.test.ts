import { describe, expect, it } from "vitest";
import { cardSchedule, cardCapacity, cardState } from "../src/domain/activity-card";
describe("activity card data", () => {
  it("uses Shanghai dates for UTC-naive tournament timestamps across midnight", () => {
    const result = cardSchedule({ start_time: "2026-10-09T17:00:00", end_time: "2026-10-09T19:00:00" }, "tournament");
    expect(result.dateLabel).toBe("10月10日 周六"); expect(result.timeLabel).toBe("01:00–03:00");
  });
  it("honors explicit offsets and shows the end date for overnight events", () => {
    expect(cardSchedule({ start_time: "2026-10-10T23:00:00+08:00", end_time: "2026-10-11T01:00:00+08:00" }, "tournament").timeLabel).toBe("23:00–10/11 01:00");
  });
  it("keeps post calendar times local and trims seconds", () => {
    expect(cardSchedule({ preferred_date: "2026-10-10", preferred_start: "19:00:00", preferred_end: "21:00:00" }, "post").timeLabel).toBe("19:00–21:00");
    expect(cardSchedule({ start_time: "invalid" }, "tournament").dateLabel).toBe("日期待定");
  });
  it("does not invent missing registration counts for personal records", () => {
    expect(cardCapacity({}, "tournament")).toBeNull();
    expect(cardCapacity({ players_needed: 4 }, "post")).toBeNull();
    expect(cardCapacity({ registration_count: 0, players_needed: 4 }, "post")?.percent).toBe(0);
  });
  it("bounds progress and prioritizes closed or ongoing states over capacity", () => {
    const capacity = cardCapacity({ current_participants: 21, max_participants: 20 }, "tournament");
    expect(capacity?.percent).toBe(100); expect(capacity?.remaining).toBe(0);
    expect(cardState({ status: "open" }, capacity).label).toBe("名额已满");
    expect(cardState({ status: "cancelled" }, capacity).label).toBe("已关闭");
    expect(cardState({ status: "ongoing" }, capacity).label).toBe("进行中");
  });
});
