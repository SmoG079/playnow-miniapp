/** Calendar date in the application's business timezone (Asia/Shanghai). */
export function businessDate(value: Date | number = Date.now()): string {
  const timestamp = value instanceof Date ? value.getTime() : value;
  return new Date(timestamp + 8 * 3600000).toISOString().slice(0, 10);
}

export function futureActivityStart(day: string, time: string, now = Date.now()): boolean {
  const start = Date.parse(`${day}T${time.slice(0, 5)}:00+08:00`);
  return Number.isFinite(start) && start > now;
}
