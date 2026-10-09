import { utcInput } from "../services/tournaments";
export interface ActivityCardData {
  id?: number; title?: string; status?: string; phase?: string;
  city?: string; address?: string; club_name?: string;
  start_time?: string; end_time?: string;
  preferred_date?: string; preferred_start?: string; preferred_end?: string;
  cover_image?: string; images?: string[]; venue_id?: number | null;
  user_nickname?: string; user_avatar?: string; level_required?: string;
  registration_count?: number; players_needed?: number;
  current_participants?: number; max_participants?: number;
}
export type ActivityKind = "post" | "tournament";
function shanghai(value?: string) {
  if (!value) return "";
  const stamp = Date.parse(utcInput(value));
  return Number.isFinite(stamp) ? new Date(stamp + 8 * 3600000).toISOString().slice(0, 16) : "";
}
export function cardSchedule(item: ActivityCardData, kind: ActivityKind) {
  const start = kind === "tournament" ? shanghai(item.start_time) : "";
  const end = kind === "tournament" ? shanghai(item.end_time) : "";
  const date = kind === "tournament" ? start.slice(0, 10) : item.preferred_date || "";
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(Date.parse(date + "T00:00:00Z"));
  const from = kind === "tournament" ? start.slice(11) : item.preferred_start?.slice(0, 5) || "";
  const to = kind === "tournament" ? end.slice(11) : item.preferred_end?.slice(0, 5) || "";
  const endDay = kind === "tournament" && end && start && end.slice(0, 10) !== date
    ? `${end.slice(5, 7)}/${end.slice(8, 10)} ` : "";
  const weekday = valid ? ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][new Date(date + "T00:00:00Z").getUTCDay()] : "";
  return { month: valid ? `${Number(date.slice(5, 7))}月` : "待定", day: valid ? date.slice(8) : "—", weekday,
    dateLabel: valid ? `${Number(date.slice(5, 7))}月${Number(date.slice(8))}日 ${weekday}` : "日期待定",
    timeLabel: from ? `${from}${to ? '–' + endDay + to : ''}` : "时间待定" };
}
export function cardCapacity(item: ActivityCardData, kind: ActivityKind) {
  const count = kind === "tournament" ? item.current_participants : item.registration_count;
  const total = kind === "tournament" ? item.max_participants : item.players_needed;
  if (typeof count !== "number" || typeof total !== "number" || !Number.isFinite(count) || !Number.isFinite(total) || count < 0 || total <= 0) return null;
  return { count, total, percent: Math.min(100, Math.round(count / total * 100)), remaining: Math.max(0, total - count) };
}
export function cardState(item: ActivityCardData, capacity: ReturnType<typeof cardCapacity>) {
  if (["cancelled", "closed"].includes(item.status || "")) return { label: "已关闭", active: false };
  if (["ended", "completed", "finished"].includes(item.status || "") || item.phase === "ended") return { label: "已结束", active: false };
  if (item.status === "ongoing" || item.phase === "ongoing") return { label: "进行中", active: true };
  if (item.status === "full" || capacity?.remaining === 0) return { label: "名额已满", active: false };
  if (item.status === "open" || item.phase === "open") return { label: "报名中", active: true };
  if (item.status === "draft") return { label: "筹备中", active: false };
  return { label: "查看活动", active: false };
}
