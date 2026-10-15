import type { Tournament } from "../services/tournaments";
export function drawBlockReason(t: Tournament | null): string {
  return !t?.config || t.draw_stage === "knockout" ? "" : t.draw_block_reason;
}
