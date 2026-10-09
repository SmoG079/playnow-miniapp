import { describe, expect, it } from "vitest";
import { bookingDuration, selectBookingCell, type BookingCell } from "../src/domain/booking";

function cell(index: number, venue = 1, status = "available"): BookingCell {
  const time = (minutes: number) => `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:00`;
  return { slot_id: venue * 100 + index, venue_id: venue, start_time: time(540 + index * 30),
    end_time: time(570 + index * 30), status };
}
const cells = [cell(0), cell(1), cell(2), cell(3)];

describe("booking page selection", () => {
  it("automatically selects one hour, then extends by half an hour", () => {
    const first = selectBookingCell([], cells[0], cells).slots;
    expect(first).toEqual(cells.slice(0, 2));
    expect(bookingDuration(first)).toBe(60);
    const extended = selectBookingCell(first, cells[2], cells).slots;
    expect(extended).toEqual(cells.slice(0, 3));
    expect(bookingDuration(extended)).toBe(90);
  });
  it("rejects a start without a following available half hour on the same court", () => {
    for (const grid of [[cell(0)], [cell(0), cell(1, 1, "booked")],
      [cell(0), cell(2)], [cell(0), cell(1, 2)]]) {
      const result = selectBookingCell([], grid[0], grid);
      expect(result.slots).toEqual([]);
      expect(result.error).toContain("不足1小时");
    }
    expect(selectBookingCell([], cells[3], cells).error).toContain("不足1小时");
  });
  it("preserves selection when an extension is unavailable, discontinuous or on another court", () => {
    const selected = cells.slice(0, 2);
    for (const next of [cell(2, 1, "locked"), cell(3), cell(2, 2)]) {
      const result = selectBookingCell(selected, next, cells);
      expect(result.slots).toEqual(selected);
      expect(result.error).toBeTruthy();
    }
  });
  it("truncates deselection and clears a remainder under one hour", () => {
    expect(selectBookingCell(cells, cells[2], cells).slots).toEqual(cells.slice(0, 2));
    expect(selectBookingCell(cells, cells[1], cells).slots).toEqual([]);
    expect(selectBookingCell(cells.slice(0, 2), cells[0], cells).slots).toEqual([]);
  });
  it("accepts a retained legacy one-hour slot without requiring a successor", () => {
    const legacy = { ...cells[0], end_time: "10:00:00" };
    expect(selectBookingCell([], legacy, [legacy]).slots).toEqual([legacy]);
    expect(bookingDuration([legacy])).toBe(60);
  });
});
