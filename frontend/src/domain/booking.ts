export interface Slot {
  id: string;
  court: number;
  index: number;
  price: number;
  available: boolean;
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
