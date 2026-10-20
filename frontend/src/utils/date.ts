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

/** Start at the next whole Shanghai hour, with a two-hour default duration. */
export function activitySchedule(now = Date.now(), sameDay = false): ActivitySchedule {
  let start = Math.floor(now / 3600000) * 3600000 + 3600000;
  const local = (stamp: number) => new Date(stamp + 8 * 3600000).toISOString().slice(0, 16);
  // Posts have a single date: use the next midnight if two hours cannot fit today.
  if (sameDay && businessDate(start) !== businessDate(start + 2 * 3600000)) {
    start = Date.parse(`${businessDate(start)}T00:00:00+08:00`) + 86400000;
  }
  const from = local(start), to = local(start + 2 * 3600000);
  return {
    start_date: from.slice(0, 10), start: from.slice(11),
    end_date: to.slice(0, 10), end: to.slice(11),
  };
}

/** Refresh expired creation drafts without changing an explicitly chosen future schedule. */
export function freshActivitySchedule(value: ActivitySchedule, now = Date.now(), sameDay = false): ActivitySchedule {
  const end = Date.parse(`${value.end_date}T${value.end}:00+08:00`);
  const start = Date.parse(`${value.start_date}T${value.start}:00+08:00`);
  return futureActivityStart(value.start_date, value.start, now) && end > start
    ? value : activitySchedule(now, sameDay);
}
