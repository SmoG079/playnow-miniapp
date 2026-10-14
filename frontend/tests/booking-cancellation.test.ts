import { describe, expect, it } from "vitest";
import { canCancelBooking } from "../src/domain/booking";

const booking = {status:"paid",slot_date:"2026-10-15",slot_start:"10:00:00"};
describe("self cancellation in Shanghai time",()=>{
  it.each(["paid","pending"])("allows %s more than one hour before the first slot",status=>{
    expect(canCancelBooking({...booking,status},Date.parse("2026-10-15T08:59:59+08:00"))).toBe(true);
  });
  it.each(["09:00:00","09:00:01","09:59:59","10:00:00","11:00:00"])("rejects cancellation at %s",time=>{
    expect(canCancelBooking(booking,Date.parse(`2026-10-15T${time}+08:00`))).toBe(false);
  });
  it("uses Shanghai time across a date boundary",()=>{
    expect(canCancelBooking({...booking,slot_start:"00:30:00"},Date.parse("2026-10-14T23:29:59+08:00"))).toBe(true);
    expect(canCancelBooking({...booking,slot_start:"00:30:00"},Date.parse("2026-10-14T23:30:00+08:00"))).toBe(false);
  });
  it.each(["cancelled","refunding","refunded","completed"])("does not show a new cancel action for %s",status=>{
    expect(canCancelBooking({...booking,status},0)).toBe(false);
  });
  it("fails closed when the booking time is missing or malformed",()=>{
    expect(canCancelBooking({status:"paid"},0)).toBe(false);
    expect(canCancelBooking({...booking,slot_start:"invalid"},0)).toBe(false);
  });
});
