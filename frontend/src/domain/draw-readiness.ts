import type { Tournament } from "../services/tournaments";
export function drawBlockReason(t: Tournament | null): string {
  if (t?.unchecked_count) return `还有${t.unchecked_count}位参赛者未签到`;
  return !t?.config || t.draw_stage === "knockout" ? "" : t.draw_block_reason;
}
