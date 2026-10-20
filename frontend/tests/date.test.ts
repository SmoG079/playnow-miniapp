import { describe, expect, it } from "vitest";
import { businessDate, futureActivityStart, activitySchedule, freshActivitySchedule } from "../src/utils/date";

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

describe('activity creation schedules', () => {
  const now = Date.parse('2026-10-20T06:24:35Z');
  it('uses the current Shanghai day and next selectable minute', () => {
    expect(activitySchedule(now)).toEqual({start_date:'2026-10-20',end_date:'2026-10-20',start:'14:25',end:'16:25'});
    expect(futureActivityStart(activitySchedule(now).start_date, activitySchedule(now).start, now)).toBe(true);
  });
  it('refreshes expired October 14 drafts and invalid end times', () => {
    expect(freshActivitySchedule({start_date:'2026-10-14',end_date:'2026-10-14',start:'09:00',end:'17:00'}, now)).toEqual(activitySchedule(now));
    expect(freshActivitySchedule({start_date:'2026-10-20',end_date:'2026-10-20',start:'19:00',end:'18:00'}, now)).toEqual(activitySchedule(now));
  });
  it('preserves an explicitly selected future date and time', () => {
    const chosen = {start_date:'2026-10-23',end_date:'2026-10-25',start:'19:00',end:'21:00'};
    expect(freshActivitySchedule(chosen, now)).toEqual(chosen);
  });
  it('refreshes an open creation form when the day changes', () => {
    const yesterday = activitySchedule(now);
    const tomorrow = now + 86400000;
    expect(freshActivitySchedule(yesterday, tomorrow)).toEqual(activitySchedule(tomorrow));
  });
  it('allows tournaments to cross midnight while keeping posts within a day', () => {
    const late = Date.parse('2026-12-31T15:30:00Z');
    expect(activitySchedule(late)).toEqual({start_date:'2026-12-31',end_date:'2027-01-01',start:'23:31',end:'01:31'});
    expect(activitySchedule(late,true)).toEqual({start_date:'2026-12-31',end_date:'2026-12-31',start:'23:31',end:'23:59'});
    expect(activitySchedule(Date.parse('2026-12-31T15:58:30Z'),true)).toEqual({start_date:'2027-01-01',end_date:'2027-01-01',start:'00:00',end:'02:00'});
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
