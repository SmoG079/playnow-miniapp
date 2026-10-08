import { describe, expect, it } from "vitest";
import {
  defaultConfig,
  validateConfig,
  localTime,
  teamName,
} from "../src/services/tournaments";
describe("tournament configuration and display", () => {
  it("validates people versus teams and qualifiers", () => {
    const c = defaultConfig();
    c.discipline = "doubles";
    expect(validateConfig(c, 5)).toContain("偶数");
    c.format = "groups_knockout";
    c.group_count = 2;
    c.qualifiers_per_group = 4;
    expect(validateConfig(c, 8)).toContain("晋级");
    c.qualifiers_per_group = 2;
    expect(validateConfig(c, 8)).toBeUndefined();
    c.courts = ["一", "一"];
    expect(validateConfig(c, 8)).toContain("重复");
  });
  it("renders stored UTC timestamps as Shanghai business dates including midnight", () => {
    expect(localTime("2026-10-10T18:00:00")).toBe("2026-10-11 02:00");
    expect(localTime("2026-10-10T18:00:00Z")).toBe("2026-10-11 02:00");
    expect(localTime("2026-10-11T02:00:00+08:00")).toBe("2026-10-11 02:00");
  });
  it("displays partner names and unresolved seats", () => {
    expect(
      teamName([{ id: 1, name: "一队", group_no: 1, user_ids: ["2", "3"] }], 1, [
        { id: 1, user_id: "2", user_nickname: "甲", status: "confirmed" },
        { id: 2, user_id: "3", user_nickname: "乙", status: "confirmed" },
      ]),
    ).toBe("甲 / 乙");
    expect(teamName([], null)).toBe("待定");
  });
});

import {
  buildSchedulePreview,
  bracketLayout,
  personalDraw,
} from "../src/services/tournament-preview";
describe("local schedule preview and personal bracket", () => {
  const start = "2026-10-10T00:00:00Z",
    end = "2026-10-11T00:00:00Z";
  it.each([2, 6, 8, 16])(
    "generates %i entrants with no empty first-round match",
    (n) => {
      const p = buildSchedulePreview(defaultConfig(), n, start, end);
      expect(p.total_matches).toBe(n - 1);
      expect(
        p.matches
          .filter((m) => m.round_no === 1)
          .every((m) => m.team_a_id || m.team_b_id),
      ).toBe(true);
      const l = bracketLayout(p.matches, 1);
      expect(l.edges.length).toBe(
        p.matches.filter((m) => m.source_a).length * 2,
      );
      expect(
        l.nodes.every((n) => n.y >= 0 && n.x >= 0 && n.y + 132 <= l.height),
      ).toBe(true);
    },
  );
  it("renders grouped knockout and combined-stage totals", () => {
    const c = defaultConfig();
    c.group_count = 2;
    c.courts = ["1", "2"];
    c.match_minutes = 15;
    const p = buildSchedulePreview(c, 8, start, end);
    expect(p.total_matches).toBe(6);
    expect(p.rounds).toBe(2);
    expect(p.estimated_minutes).toBe(45);
    c.format = "groups_knockout";
    const combined = buildSchedulePreview(c, 8, start, end);
    expect(combined.total_matches).toBe(15);
    expect(combined.knockout_preview?.matches.length).toBe(3);
  });
  it("round robin odd entrants meet once without simultaneous appearances", () => {
    const c = defaultConfig();
    c.format = "round_robin";
    c.courts = ["1", "2"];
    const p = buildSchedulePreview(c, 5, start, end);
    expect(p.total_matches).toBe(10);
    expect(p.rounds).toBe(5);
    for (const m of p.matches)
      for (const other of p.matches)
        if (
          m !== other &&
          m.scheduled_at! < other.scheduled_end! &&
          m.scheduled_end! > other.scheduled_at!
        ) {
          expect([other.team_a_id, other.team_b_id]).not.toContain(m.team_a_id);
          expect([other.team_a_id, other.team_b_id]).not.toContain(m.team_b_id);
        }
  });
  it("locates lower half and removes winner route after elimination", () => {
    const p = buildSchedulePreview(defaultConfig(), 8, start, end);
    p.teams[3].user_ids = ["91"];
    const me = personalDraw(p.teams, p.matches, "91")!;
    expect(me.half).toBe("下半区");
    expect(me.matches.length).toBe(3);
    const first = me.matches[0];
    first.status = "completed";
    first.winner_id = first.team_b_id;
    expect(personalDraw(p.teams, p.matches, "91")?.matches.length).toBe(1);
  });
});
