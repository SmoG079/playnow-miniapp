/** Calendar date in the application's business timezone (Asia/Shanghai). */
export function businessDate(value: Date | number = Date.now()): string {
  const timestamp = value instanceof Date ? value.getTime() : value;
  return new Date(timestamp + 8 * 3600000).toISOString().slice(0, 10);
}
