export type DiscoverySort = "date_asc" | "date_desc" | "distance";
export const sortOptions = ["按日期最近", "按距离最近", "按日期最远"];
export const sortValues: DiscoverySort[] = ["date_asc", "distance", "date_desc"];
export const levelOptions = ["不限", ...Array.from({ length: 13 }, (_, i) => (1 + i * 0.5).toFixed(1))];
export function discoveryQuery(city: string, sort: DiscoverySort, date: string, latitude: number | null, longitude: number | null) {
  if (!city.trim()) return "";
  let query = `city=${encodeURIComponent(city.trim())}&sort_by=${sort}`;
  if (date) query += `&on_date=${date}`;
  if (sort === "distance" && latitude !== null && longitude !== null) query += `&lat=${latitude}&lng=${longitude}`;
  return query;
}
export function ownLevel(level: unknown): string | null {
  const n = Number(level);
  return Number.isFinite(n) && n >= 1 && n <= 7 && Number.isInteger(n * 2) ? n.toFixed(1) : null;
}
