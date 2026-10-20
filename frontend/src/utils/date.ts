/** Calendar date in the application's business timezone (Asia/Shanghai). */
export function businessDate(value: Date | number = Date.now()): string {
  const timestamp = value instanceof Date ? value.getTime() : value;
  return new Date(timestamp + 8 * 3600000).toISOString().slice(0, 10);
}

export function futureActivityStart(day: string, time: string, now = Date.now()): boolean {
  const start = Date.parse(`${day}T${time.slice(0, 5)}:00+08:00`);
  return Number.isFinite(start) && start > now;
}

export type ActivitySchedule = { start_date: string; end_date: string; start: string; end: string };

/** Start at the next selectable minute; keep the default end after the start. */
export function activitySchedule(now = Date.now(), sameDay = false): ActivitySchedule {
  let start = Math.floor(now / 60000) * 60000 + 60000;
  const local = (stamp: number) => new Date(stamp + 8 * 3600000).toISOString().slice(0, 16);
  if (sameDay && local(start).slice(11) === '23:59') start += 60000;
  const from = local(start), to = local(start + 2 * 3600000);
  return {
    start_date: from.slice(0, 10), start: from.slice(11),
    end_date: sameDay ? from.slice(0, 10) : to.slice(0, 10),
    end: sameDay && from.slice(0, 10) !== to.slice(0, 10) ? '23:59' : to.slice(11),
  };
}

/** Refresh expired creation drafts without changing an explicitly chosen future schedule. */
export function freshActivitySchedule(value: ActivitySchedule, now = Date.now(), sameDay = false): ActivitySchedule {
  const end = Date.parse(`${value.end_date}T${value.end}:00+08:00`);
  const start = Date.parse(`${value.start_date}T${value.start}:00+08:00`);
  return futureActivityStart(value.start_date, value.start, now) && end > start
    ? value : activitySchedule(now, sameDay);
}
