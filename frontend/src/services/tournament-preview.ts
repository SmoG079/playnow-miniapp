import {
  type Match,
  type Team,
  type TournamentConfig,
  validateConfig,
} from "./tournaments";

export interface SchedulePreview {
  teams: Team[];
  matches: Match[];
  total_matches: number;
  rounds: number;
  estimated_minutes: number;
  overflows: boolean;
  note: string;
  knockout_preview?: { teams: Team[]; matches: Match[] };
}
function knockout(ids: number[], group: number, third: boolean): Match[] {
  const size = 2 ** Math.ceil(Math.log2(ids.length));
  const slots: (number | null)[] = Array(size).fill(null);
  ids.forEach((id, i) => {
    slots[i < size / 2 ? i * 2 : (i - size / 2) * 2 + 1] = id;
  });
  const ms: Match[] = [];
  let previous: string[] = [];
  let round = 1;
  for (let i = 0; i < size / 2; i++) {
    const key = `${group}:1:${i}`;
    const a = slots[2 * i],
      b = slots[2 * i + 1];
    ms.push({
      key,
      group_no: group,
      round_no: 1,
      position: i,
      kind: "knockout",
      team_a_id: a,
      team_b_id: b,
      status: a && b ? "pending" : "bye",
      winner_id: a && b ? null : a || b,
    });
    previous.push(key);
  }
  while (previous.length > 1) {
    round++;
    const next: string[] = [];
    for (let i = 0; i < previous.length / 2; i++) {
      const key = `${group}:${round}:${i}`;
      ms.push({
        key,
        group_no: group,
        round_no: round,
        position: i,
        kind: "knockout",
        source_a: previous[2 * i],
        source_b: previous[2 * i + 1],
        status: "pending",
      });
      next.push(key);
    }
    previous = next;
  }
  if (third && size >= 4) {
    const final = ms[ms.length - 1];
    ms.push({
      key: `${group}:third`,
      group_no: group,
      round_no: round,
      position: 1,
      kind: "third_place",
      source_a: final.source_a,
      source_b: final.source_b,
      source_outcome: "loser",
      status: "pending",
    });
  }
  // Only a known bye winner can be filled before real results exist.
  for (const m of ms)
    for (const side of ["a", "b"] as const) {
      const source = ms.find((x) => x.key === m[`source_${side}`]);
      if (source?.status === "bye" && m.source_outcome !== "loser")
        m[`team_${side}_id`] = source.winner_id;
    }
  return ms;
}
function roundRobin(ids: number[], group: number): Match[] {
  let rotating: (number | null)[] = [...ids];
  if (ids.length % 2) rotating.push(null);
  const ms: Match[] = [];
  for (let r = 1; r < rotating.length; r++) {
    for (let i = 0; i < rotating.length / 2; i++) {
      const a = rotating[i],
        b = rotating[rotating.length - 1 - i];
      if (a && b)
        ms.push({
          key: `${group}:${r}:${i}`,
          group_no: group,
          round_no: r,
          position: i,
          kind: "round_robin",
          team_a_id: a,
          team_b_id: b,
          status: "pending",
        });
    }
    rotating = [
      rotating[0],
      rotating[rotating.length - 1],
      ...rotating.slice(1, -1),
    ];
  }
  return ms;
}
function schedule(ms: Match[], c: TournamentConfig, start: number): number {
  const courts = c.courts.slice(0, c.max_parallel || c.courts.length);
  const available = courts.map(() => start),
    duration = c.match_minutes * 60000;
  const rounds = new Map<string, number>();
  const byKey = new Map(ms.map((m) => [m.key, m]));
  let finish = start;
  for (const m of [...ms].sort(
    (a, b) =>
      a.round_no - b.round_no ||
      a.group_no - b.group_no ||
      a.position - b.position,
  )) {
    if (m.status === "bye") continue;
    let ready = start;
    for (let r = 1; r < m.round_no; r++)
      ready = Math.max(ready, rounds.get(`${m.group_no}:${r}`) || start);
    for (const source of [m.source_a, m.source_b]) {
      const p = source ? byKey.get(source) : undefined;
      if (p?.scheduled_end)
        ready = Math.max(ready, Date.parse(p.scheduled_end));
    }
    const i = available.reduce(
      (best, v, index) =>
        Math.max(v, ready) < Math.max(available[best], ready) ? index : best,
      0,
    );
    const at = Math.max(ready, available[i]);
    available[i] = at + duration;
    m.court = courts[i];
    m.scheduled_at = new Date(at).toISOString();
    m.scheduled_end = new Date(at + duration).toISOString();
    rounds.set(
      `${m.group_no}:${m.round_no}`,
      Math.max(
        rounds.get(`${m.group_no}:${m.round_no}`) || start,
        at + duration,
      ),
    );
    finish = Math.max(finish, at + duration);
  }
  return finish;
}
export function buildSchedulePreview(
  c: TournamentConfig,
  people: number,
  startTime: string,
  endTime: string,
): SchedulePreview {
  const error = validateConfig(c, people);
  if (error) throw new Error(error);
  const start = Date.parse(startTime),
    end = Date.parse(endTime);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start)
    throw new Error("结束时间必须晚于开始时间");
  const count = people / (c.discipline === "singles" ? 1 : 2);
  const teams: Team[] = Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    name: `虚拟${c.discipline === "singles" ? "选手" : "队伍"}${i + 1}`,
    group_no: (i % c.group_count) + 1,
  }));
  const ms: Match[] = [];
  for (let g = 1; g <= c.group_count; g++) {
    const ids = teams.filter((t) => t.group_no === g).map((t) => t.id);
    ms.push(
      ...(c.format === "knockout"
        ? knockout(ids, g, c.third_place)
        : roundRobin(ids, g)),
    );
  }
  let finish = schedule(ms, c, start);
  let playoff: SchedulePreview["knockout_preview"];
  if (c.format === "groups_knockout") {
    const qualified = Array.from(
      { length: c.group_count * c.qualifiers_per_group },
      (_, i) => ({
        id: i + 1,
        name: `第${(i % c.group_count) + 1}组第${Math.floor(i / c.group_count) + 1}名`,
        group_no: 1,
      }),
    );
    const matches = knockout(
      qualified.map((t) => t.id),
      1,
      c.third_place,
    );
    finish = schedule(matches, c, finish);
    playoff = { teams: qualified, matches };
  }
  return {
    teams,
    matches: ms,
    knockout_preview: playoff,
    total_matches: [...ms, ...(playoff?.matches || [])].filter(
      (m) => m.status !== "bye",
    ).length,
    rounds:
      Math.max(...ms.map((m) => m.round_no)) +
      (playoff ? Math.max(...playoff.matches.map((m) => m.round_no)) : 0),
    estimated_minutes: Math.ceil((finish - start) / 60000),
    overflows: finish > end,
    note: "按当前赛制配置以虚拟选手模拟生成，正式对阵以最新发布签表为准。",
  };
}

export function personalDraw(teams: Team[], matches: Match[], userId?: string) {
  const team = teams.find((t) => t.user_ids?.includes(userId || ""));
  if (!team) return null;
  const group = matches.filter((m) => m.group_no === team.group_no);
  const first = group.find(
    (m) => m.round_no === 1 && [m.team_a_id, m.team_b_id].includes(team.id),
  );
  const firstRound = group.filter(
    (m) => m.round_no === 1 && m.kind === "knockout",
  );
  const half =
    firstRound.length > 1 && first
      ? first.position < firstRound.length / 2
        ? "上半区"
        : "下半区"
      : first?.kind === "knockout"
        ? "决赛签位"
        : "循环组";
  const keys = new Set<string>();
  const path: Match[] = [];
  const byKey = new Map(group.map((m) => [m.key, m]));
  for (const m of group) {
    let included = [m.team_a_id, m.team_b_id].includes(team.id);
    for (const source of [m.source_a, m.source_b]) {
      const parent = source ? byKey.get(source) : undefined;
      if (source && keys.has(source) && parent) {
        included ||= ["completed", "bye"].includes(parent.status)
          ? m.source_outcome === "loser"
            ? parent.winner_id !== team.id
            : parent.winner_id === team.id
          : true;
      }
    }
    if (included) {
      keys.add(m.key);
      path.push(m);
    }
  }
  return { team, half, matches: path };
}
export function roundLabel(matches: Match[], m: Match): string {
  if (m.kind === "third_place") return "季军赛";
  if (m.kind === "round_robin") return `第 ${m.round_no} 轮`;
  const max = Math.max(
    ...matches
      .filter((x) => x.kind === "knockout" && x.group_no === m.group_no)
      .map((x) => x.round_no),
  );
  const left = max - m.round_no;
  return left === 0
    ? "决赛"
    : left === 1
      ? "半决赛"
      : left === 2
        ? "四分之一决赛"
        : `第 ${m.round_no} 轮`;
}

export function bracketLayout(matches: Match[], group: number) {
  const ms = matches.filter((m) => m.group_no === group);
  const rounds = [...new Set(ms.map((m) => m.round_no))].sort((a, b) => a - b);
  const first = ms.filter(
    (m) => m.round_no === rounds[0] && m.kind !== "third_place",
  );
  const baseHeight = Math.max(first.length * 164, 220);
  const nodes: { match: Match; x: number; y: number }[] = [];
  for (const m of ms) {
    const col = rounds.indexOf(m.round_no);
    let y =
      ms
        .filter((x) => x.round_no === m.round_no && x.kind !== "third_place")
        .indexOf(m) * 164;
    if (m.kind === "third_place") y = baseHeight + 30;
    else if (m.kind === "knockout" && col > 0) {
      const parents = nodes.filter((n) =>
        [m.source_a, m.source_b].includes(n.match.key),
      );
      if (parents.length)
        y = parents.reduce((sum, n) => sum + n.y, 0) / parents.length;
    }
    nodes.push({ match: m, x: col * 260, y });
  }
  const edges: {
    key: string;
    x: number;
    from: number;
    to: number;
    targetX: number;
  }[] = [];
  for (const n of nodes)
    if (n.match.kind !== "round_robin")
      for (const [source, offset] of [
        [n.match.source_a, 44],
        [n.match.source_b, 85],
      ] as const) {
        const parent = nodes.find((p) => p.match.key === source);
        if (parent)
          edges.push({
            key: parent.match.key + ">" + n.match.key + offset,
            x: parent.x + 210,
            from: parent.y + 66,
            to: n.y + offset,
            targetX: n.x,
          });
      }
  return {
    nodes,
    edges,
    rounds,
    width: Math.max(210, rounds.length * 260 - 50),
    height: Math.max(baseHeight, ...nodes.map((n) => n.y + 145)),
  };
}
