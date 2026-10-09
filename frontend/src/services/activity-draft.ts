import { sessionContext } from "./session-context";

type DraftKind = "post" | "tournament";
function key(kind: DraftKind, owner: string, editId: number) {
  return `activity_draft_v1:${encodeURIComponent(sessionContext())}:${encodeURIComponent(owner)}:${kind}:${editId}`;
}

/** Local drafts are isolated by account, environment, activity kind and edit target. */
export function saveActivityDraft(kind: DraftKind, owner: string, editId: number, value: any): boolean {
  if (!owner) return false;
  try {
    uni.setStorageSync(key(kind, owner, editId), { version: 1, savedAt: Date.now(), value: JSON.parse(JSON.stringify(value)) });
    return true;
  } catch { return false; }
}

export function readActivityDraft(kind: DraftKind, owner: string, editId: number): any | null {
  if (!owner) return null;
  try {
    const draft = uni.getStorageSync(key(kind, owner, editId));
    return draft?.version === 1 && draft.value && typeof draft.value === "object" ? JSON.parse(JSON.stringify(draft.value)) : null;
  } catch { return null; }
}

export function clearActivityDraft(kind: DraftKind, owner: string, editId: number) {
  if (owner) uni.removeStorageSync(key(kind, owner, editId));
}
