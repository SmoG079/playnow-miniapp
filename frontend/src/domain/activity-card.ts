import { utcInput, disciplineNames, formatNames, type TournamentConfig } from "../services/tournaments";
export interface CardParticipant {
  user_id: string;
  user_nickname?: string | null;
  user_avatar?: string | null;
}
export interface ActivityCardData {
  id?: number; title?: string; status?: string; phase?: string;
  registration_deadline?: string; registration_closed?: boolean;
  result_summary?: {score?: string; winner?: string; is_draw?: boolean; walkover?: boolean};
  club_id?: number | null; organizer_nickname?: string | null; organizer_avatar?: string | null; club_avatar?: string | null;
  city?: string; address?: string; location_name?: string; club_name?: string; contact_name?: string;
  start_time?: string; end_time?: string;
  preferred_date?: string; preferred_start?: string; preferred_end?: string;
  cover_image?: string; images?: string[]; venue_id?: number | null;
  user_nickname?: string; user_avatar?: string; level_required?: string;
  registration_count?: number; min_players?: number; max_players?: number;
  current_participants?: number; max_participants?: number;
  price?: number | string | null; entry_fee?: number | string | null;
  config?: Pick<TournamentConfig, "discipline" | "format" | "pairing"> | null;
  card_participants?: CardParticipant[];
}
export type ActivityKind = "post" | "tournament";
export function cardDetails(item: ActivityCardData, kind: ActivityKind) {
  const tournament = kind === "tournament", cfg = item.config;
  const typeLabel = tournament ? `${cfg ? disciplineNames[cfg.discipline] : ''}比赛`
    : item.venue_id === undefined ? "约球活动" : item.venue_id ? "定场约球" : "自由约球";
  const tags: string[] = [];
  if (item.level_required) tags.push(`NTRP ${item.level_required}`);
  if (tournament && cfg) {
    if (cfg.discipline !== "singles" && cfg.pairing) tags.push(cfg.pairing === "fixed" ? "固定搭档" : "随机搭档");
    tags.push(formatNames[cfg.format]);
  } else if (!tournament && item.min_players && item.max_players) {
    tags.push(item.min_players === item.max_players ? `${item.max_players}人` : `${item.min_players}–${item.max_players}人`);
  }
  const raw = tournament ? item.entry_fee : item.price;
  const fee = raw === null || raw === undefined || raw === "" ? NaN : Number(raw);
  return { typeLabel, tags,
    host: tournament ? (item.club_id ? item.club_name || "俱乐部" : item.organizer_nickname || "球友") : item.user_nickname || "球友",
    place: item.location_name || "地点待补充", address: item.address || item.city || "",
    feeLabel: Number.isFinite(fee) && fee >= 0 ? fee === 0 ? "免费" : `¥${Number(fee.toFixed(2))}` : "",
    feeSuffix: fee > 0 && Number.isFinite(fee) ? "/ 人" : "" };
}

export function cardStatus(item: ActivityCardData, kind: ActivityKind) {
  const capacity = cardCapacity(item, kind), state = cardState(item, capacity, kind);
  if (state.label !== "报名中" || !capacity) return state;
  const formed = kind === "post" && typeof item.min_players === "number" && capacity.count >= item.min_players;
  return { ...state, label: `${formed ? '已成团' : state.label} · 余${capacity.remaining}位` };
}
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
  const count = kind === "tournament" ? item.current_participants : typeof item.registration_count === "number" ? item.registration_count + 1 : undefined;
  const total = kind === "tournament" ? item.max_participants : item.max_players;
  if (typeof count !== "number" || typeof total !== "number" || !Number.isFinite(count) || !Number.isFinite(total) || count < 0 || total <= 0) return null;
  return { count, total, percent: Math.min(100, Math.round(count / total * 100)), remaining: Math.max(0, total - count) };
}
export function cardState(item: Pick<ActivityCardData, "status" | "phase">, capacity: ReturnType<typeof cardCapacity>, kind: ActivityKind = "tournament") {
  if (["cancelled", "closed"].includes(item.status || "")) return { label: "已关闭", active: false };
  if (["ended", "completed", "finished"].includes(item.status || "") || item.phase === "ended") return { label: "已结束", active: false };
  if (item.phase === "ongoing" || !item.phase && item.status === "ongoing") return { label: kind === "tournament" ? "比赛进行中" : "进行中", active: true };
  if (item.phase === "registration_closed") return { label: "报名截止，等待开始", active: false };
  if (item.status === "full" || capacity?.remaining === 0) return { label: "名额已满", active: false };
  if (item.status === "open" || item.phase === "open") return { label: "报名中", active: true };
  if (item.status === "draft") return { label: "筹备中", active: false };
  return { label: "查看活动", active: false };
}
