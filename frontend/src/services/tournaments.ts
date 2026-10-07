import { request } from "./api";
export type TournamentFormat = "knockout" | "round_robin" | "groups_knockout";
export type Discipline = "singles" | "doubles" | "mixed";
export interface TournamentConfig {
  format: TournamentFormat;
  discipline: Discipline;
  group_count: number;
  courts: string[];
  match_minutes: number;
  third_place: boolean;
  allow_draw: boolean;
  max_parallel: number | null;
  qualifiers_per_group: number;
  approval_required: boolean;
  waitlist_enabled: boolean;
  ungrouped_display: boolean;
}
export const formatNames = {
  knockout: "淘汰赛",
  round_robin: "循环赛",
  groups_knockout: "循环接淘汰",
};
export const disciplineNames = {
  singles: "单打",
  doubles: "双打",
  mixed: "混双",
};
export function defaultConfig(): TournamentConfig {
  return {
    format: "knockout",
    discipline: "singles",
    group_count: 1,
    courts: ["1号场地"],
    match_minutes: 45,
    third_place: false,
    allow_draw: false,
    max_parallel: null,
    qualifiers_per_group: 2,
    approval_required: false,
    waitlist_enabled: false,
    ungrouped_display: false,
  };
}
export interface Team {
  id: number;
  name: string;
  group_no: number;
  user_ids?: number[];
  origin_group?: number;
}
export interface Match {
  id?: number;
  key: string;
  group_no: number;
  round_no: number;
  position: number;
  kind: string;
  team_a_id?: number | null;
  team_b_id?: number | null;
  source_a?: string | null;
  source_b?: string | null;
  source_outcome?: string;
  winner_id?: number | null;
  status: string;
  score?: string;
  is_draw?: boolean;
  walkover?: boolean;
  court?: string;
  scheduled_at?: string;
  scheduled_end?: string;
}
export interface Registration {
  requested_group?: number;
  id: number;
  user_id: number;
  user_nickname?: string;
  user_avatar?: string;
  status: string;
  admission?: string;
  approval?: string;
  payment?: string;
  pairing?: string;
  gender?: string;
  partner_user_id?: number;
  invite_token?: string;
  review_reason?: string;
  seat_expires_at?: string;
  refund_status?: string;
}
export interface Tournament {
  id: number;
  club_id: number;
  club_name: string;
  title: string;
  description: string;
  description_template?: string;
  start_time: string;
  end_time: string;
  entry_fee: number;
  status: string;
  address: string;
  images: string[];
  contact_name: string;
  contact_phone: string;
  prize: string;
  auto_title: boolean;
  cover_image?: string;
  max_participants: number;
  current_participants: number;
  config: TournamentConfig | null;
  registration_deadline: string;
  cancellation_deadline: string;
  roster_frozen: boolean;
  draw_version: number;
  published_version: number;
  draw_stage?: string;
  draw_published: boolean;
  can_manage: boolean;
  can_register: boolean;
  bracket_preview?: { teams: Team[]; matches: Match[] };
  participant_preview?: {
    teams: Team[];
    matches: Match[];
    note: string;
  } | null;
  prepay_enabled: boolean;
  registration_groups?: {
    group_no: number;
    capacity: number;
    reserved: number;
  }[];
  registrations: Registration[];
  my_registration?: Registration | null;
  teams: Team[];
  matches: Match[];
  rankings: {
    team_id: number;
    group_no: number;
    rank: number | null;
    points?: number;
    tie_unresolved: boolean;
  }[];
  history: {
    version: number;
    stage: string;
    published: boolean;
    reason?: string;
  }[];
}
export function utcInput(value: string): string {
  return /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : value + "Z";
}
export function localTime(value?: string): string {
  if (!value) return "待排场";
  const d = new Date(utcInput(value));
  // Explicit business timezone; avoid host/device timezone assumptions.
  const shanghai = new Date(d.getTime() + 8 * 3600000);
  return shanghai.toISOString().slice(0, 16).replace("T", " ");
}
export function teamName(
  teams: Team[],
  id?: number | null,
  regs: Registration[] = [],
): string {
  if (!id) return "待定";
  const t = teams.find((t) => t.id === id);
  return (
    t?.user_ids
      ?.map(
        (u) => regs.find((r) => r.user_id === u)?.user_nickname || `选手${u}`,
      )
      .join(" / ") ||
    t?.name ||
    "待定"
  );
}
export function validateConfig(
  c: TournamentConfig,
  people: number,
): string | undefined {
  if (!Number.isInteger(people) || people < 2 || people > 128)
    return "人数须为 2–128 的整数";
  if (c.discipline !== "singles" && people % 2) return "双打人数必须为偶数";
  const teams = people / (c.discipline === "singles" ? 1 : 2);
  if (
    !Number.isInteger(c.group_count) ||
    c.group_count < 1 ||
    c.group_count > 16 ||
    teams / c.group_count < 2
  )
    return "每组至少需要两队";
  if (
    !c.courts.length ||
    c.courts.some((x) => !x.trim()) ||
    new Set(c.courts).size !== c.courts.length
  )
    return "场地名称不能为空或重复";
  if (
    c.format === "groups_knockout" &&
    (c.group_count < 2 ||
      c.qualifiers_per_group > Math.floor(teams / c.group_count))
  )
    return "请检查分组和晋级人数";
}
export function getTournament(id: number) {
  return request<Tournament>(`/tournaments/${id}`);
}
export function command<T = any>(
  id: number,
  path: string,
  data?: unknown,
  method: "POST" | "PUT" = "POST",
) {
  return request<T>(`/tournaments/${id}/${path}`, { method, data });
}
