import { request } from "./api";
export interface UtrStats {
  rating: number | null;
  matches_played: number | null;
  wins: number | null;
  losses: number | null;
  world_rank: number | null;
  age_group: string | null;
}
export interface UtrRecord extends UtrStats {
  nickname: string | null;
  avatar_url: string | null;
  ntrp_level: number | null;
}
export const UTR_SOURCE_NOTE = "所有数据（包括世界排名）均来自 UTR 官网。世界排名仅代表所在年龄段在 UTR 系统中按积分排序产生的世界排名，不能严格代表真实水平差异。";
export function getMyUtrRecord() {
  return request<UtrRecord>("/users/me/utr-record");
}
/** Null means unsynced; an actual zero is preserved. No rating or rank is inferred. */
export function utrValue(value: number | string | null | undefined, precision?: number): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return "—";
  return precision === undefined ? String(number) : number.toFixed(precision);
}
export function utrRank(value: number | null | undefined): string {
  const text = utrValue(value);
  return text === "—" ? text : text.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
