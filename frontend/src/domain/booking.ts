export interface Slot {
  id: string;
  court: number;
  index: number;
  price: number;
  available: boolean;
}

export interface BookingCell {
  slot_id: number;
  venue_id: number;
  start_time: string;
  end_time: string;
  status: string;
}

function minutes(time: string) {
  const [hour, minute] = time.split(":").map(Number);
  return hour * 60 + minute;
}

export function bookingDuration(slots: BookingCell[]) {
  return slots.reduce((sum, slot) => sum + minutes(slot.end_time) - minutes(slot.start_time), 0);
}

/** Keep a selection empty or at least one continuous hour. */
export function selectBookingCell<T extends BookingCell>(
  selected: T[], cell: T, cells: T[],
): { slots: T[]; error?: string } {
  if (!cell.slot_id || cell.status !== "available")
    return { slots: selected, error: "该时段暂不可预订" };
  const existing = selected.findIndex(slot => slot.slot_id === cell.slot_id);
  if (existing >= 0) {
    const remaining = selected.slice(0, existing);
    return { slots: bookingDuration(remaining) >= 60 ? remaining : [] };
  }
  if (selected.length) {
    const last = selected[selected.length - 1];
    if (last.venue_id !== cell.venue_id || minutes(last.end_time) !== minutes(cell.start_time))
      return { slots: selected, error: "请选择同一场地的连续时段" };
    return { slots: [...selected, cell] };
  }
  const initial = [cell];
  while (bookingDuration(initial) < 60) {
    const last = initial[initial.length - 1];
    const next = cells.find(slot =>
      slot.venue_id === cell.venue_id && slot.slot_id && slot.status === "available" &&
      minutes(slot.start_time) === minutes(last.end_time) &&
      minutes(slot.end_time) > minutes(slot.start_time) &&
      !initial.some(chosen => chosen.slot_id === slot.slot_id),
    );
    if (!next) return { slots: selected, error: "后续可订时段不足1小时，请选择其他时段" };
    initial.push(next);
  }
  return { slots: initial };
}
export function selectSlot(
  selected: Slot[],
  slot: Slot,
): { slots: Slot[]; error?: string } {
  if (!slot.available) return { slots: selected, error: "该时段暂不可预订" };
  const existing = selected.findIndex((s) => s.id === slot.id);
  if (existing >= 0) return { slots: selected.slice(0, existing) };
  if (selected.length && selected[0].court !== slot.court)
    return { slots: selected, error: "请选择同一片场地的连续时段" };
  if (selected.length && slot.index !== selected[selected.length - 1].index + 1)
    return { slots: selected, error: "请按顺序选择连续时段" };
  return { slots: [...selected, slot] };
}
export function totalPrice(slots: Slot[]) {
  return slots.reduce((sum, s) => sum + s.price, 0);
}
export function canBook(slots: Slot[]) {
  return slots.length >= 2;
}
export function filterActivities<
  T extends { day: number; level: number; kind: string },
>(items: T[], day: number, level: string, kind: string) {
  return items.filter(
    (a) =>
      a.kind === kind &&
      (day < 0 || a.day === day) &&
      (!level || a.level === Number(level)),
  );
}
