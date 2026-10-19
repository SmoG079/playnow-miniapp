import { describe, expect, it } from "vitest";
import { cardSchedule, cardCapacity, cardState, cardDetails, cardStatus } from "../src/domain/activity-card";
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
    expect(cardCapacity({ max_players: 5 }, "post")).toBeNull();
    expect(cardCapacity({ registration_count: 0, max_players: 5 }, "post")).toEqual({count:1,total:5,percent:20,remaining:4});
  });
  it("bounds progress and prioritizes closed or ongoing states over capacity", () => {
    const capacity = cardCapacity({ current_participants: 21, max_participants: 20 }, "tournament");
    expect(capacity?.percent).toBe(100); expect(capacity?.remaining).toBe(0);
    expect(cardState({ status: "open" }, capacity).label).toBe("名额已满");
    expect(cardState({ status: "cancelled" }, capacity).label).toBe("已关闭");
    expect(cardState({ status: "ongoing" }, capacity).label).toBe("比赛进行中");
  });
  it("uses each activity's fee without inventing a free price", () => {
    expect(cardDetails({ price: 0, entry_fee: 120 }, "post").feeLabel).toBe("免费");
    expect(cardDetails({ price: 50, entry_fee: "120.50" }, "tournament")).toMatchObject({ feeLabel: "¥120.5", feeSuffix: "/ 人" });
    for (const price of [undefined, null, "", "invalid", -1]) expect(cardDetails({ price }, "post").feeLabel).toBe("");
  });
  it("keeps location names separate from addresses and distinguishes event formats", () => {
    const item = { location_name: "扬州网球中心", address: "邗江区长春路48号", config: { discipline: "doubles", pairing: "fixed", format: "knockout" } } as const;
    expect(cardDetails(item, "tournament")).toMatchObject({ typeLabel: "双打比赛", place: "扬州网球中心", address: "邗江区长春路48号", tags: ["固定搭档", "淘汰赛"] });
    expect(cardDetails({ min_players: 4, max_players: 6, venue_id: null }, "post")).toMatchObject({ typeLabel: "自由约球", tags: ["4–6人"] });
    expect(cardDetails({ config: { discipline: "singles", pairing: null, format: "round_robin" } }, "tournament").tags).toEqual(["循环赛"]);
  });
  it("shows the post formation goal including its organizer without overriding lifecycle states", () => {
    const item = { status: "open", min_players: 4, max_players: 6, registration_count: 3 };
    expect(cardStatus(item, "post").label).toBe("已成团 · 余2位");
    expect(cardStatus({ ...item, registration_count: 2 }, "post").label).toBe("报名中 · 余3位");
    expect(cardStatus({ ...item, phase: "ended" }, "post").label).toBe("已结束");
    expect(cardStatus({ ...item, registration_count: 5 }, "post").label).toBe("名额已满");
    expect(cardStatus({ ...item, phase: "registration_closed" }, "post").label).toBe("报名截止，等待开始");
  });
});
it('uses the account identity for personal organizers and keeps club identity distinct',()=>{
 expect(cardDetails({club_id:null,organizer_nickname:'真实昵称',contact_name:'手填联系人'},'tournament').host).toBe('真实昵称');
 expect(cardDetails({club_id:1,club_name:'网球俱乐部',organizer_nickname:'管理员昵称'},'tournament').host).toBe('网球俱乐部');
});
