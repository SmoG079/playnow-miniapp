import { sessionContext } from "./session-context";
import { saveActivityDraft, readActivityDraft, clearActivityDraft } from "./activity-draft";
export const TOURNAMENT_DRAFT_KEY = "tournament_draft_cache";
export function saveTournamentDraft(owner: string, editId: number, value: any) {
  return saveActivityDraft("tournament", owner, editId, value);
}
export function readTournamentDraft(owner: string, editId: number): any | null {
  const current = readActivityDraft("tournament", owner, editId);
  if (current) return current;
  const cached = uni.getStorageSync(TOURNAMENT_DRAFT_KEY);
  if (!cached || cached.owner !== owner || cached.editId !== editId || cached.context !== sessionContext() || cached.expires <= Date.now()) return null;
  if (!saveTournamentDraft(owner, editId, cached.value)) return cached.value;
  uni.removeStorageSync(TOURNAMENT_DRAFT_KEY);
  return cached.value;
}
export function clearTournamentDraft(owner: string, editId: number) {
  clearActivityDraft("tournament", owner, editId);
  const cached = uni.getStorageSync(TOURNAMENT_DRAFT_KEY);
  if (cached?.owner === owner && cached.editId === editId && cached.context === sessionContext()) uni.removeStorageSync(TOURNAMENT_DRAFT_KEY);
}
