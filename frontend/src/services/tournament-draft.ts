import { sessionContext } from "./session-context";
export const TOURNAMENT_DRAFT_KEY = "tournament_draft_cache";
const TTL = 24 * 60 * 60 * 1000;
export function saveTournamentDraft(owner: string, editId: number, value: any) {
  if (!owner) return;
  uni.setStorageSync(TOURNAMENT_DRAFT_KEY, { owner, editId, context: sessionContext(), expires: Date.now() + TTL, value: JSON.parse(JSON.stringify(value)) });
}
export function readTournamentDraft(owner: string, editId: number): any | null {
  const cached = uni.getStorageSync(TOURNAMENT_DRAFT_KEY);
  if (!cached || cached.owner !== owner || cached.editId !== editId || cached.context !== sessionContext() || cached.expires <= Date.now()) return null;
  return cached.value;
}
export function clearTournamentDraft() { uni.removeStorageSync(TOURNAMENT_DRAFT_KEY); }
