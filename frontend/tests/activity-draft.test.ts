import { beforeEach, describe, expect, it, vi } from "vitest";
import { saveActivityDraft, readActivityDraft, clearActivityDraft } from "../src/services/activity-draft";

describe("persistent activity drafts", () => {
  const storage = new Map<string, any>();
  beforeEach(() => {
    storage.clear();
    vi.stubGlobal("uni", { setStorageSync: (key: string, value: any) => storage.set(key, value),
      getStorageSync: (key: string) => storage.get(key), removeStorageSync: (key: string) => storage.delete(key) });
  });
  it("restores all post form fields without mixing accounts, activity kinds or edit targets", () => {
    const draft = { form: { title: "周末练球", booking_id: 12, city: "扬州市", latitude: 32 },
      images: ["https://example.com/cover.jpg"], club: { id: 14 }, choosingVenue: true, venueName: "2号场" };
    expect(saveActivityDraft("post", "alice", 0, draft)).toBe(true);
    draft.form.title = "later";
    expect(readActivityDraft("post", "alice", 0).form.title).toBe("周末练球");
    expect(readActivityDraft("post", "alice", 0).images).toEqual(draft.images);
    expect(readActivityDraft("post", "bob", 0)).toBeNull();
    expect(readActivityDraft("tournament", "alice", 0)).toBeNull();
    expect(readActivityDraft("post", "alice", 1)).toBeNull();
    saveActivityDraft("post", "bob", 0, { form: { title: "bob" } });
    clearActivityDraft("post", "alice", 0);
    expect(readActivityDraft("post", "alice", 0)).toBeNull();
    expect(readActivityDraft("post", "bob", 0).form.title).toBe("bob");
  });
  it("isolates mini-program AppIDs and reports storage failures", () => {
    uni.getAccountInfoSync = () => ({ miniProgram: { appId: "first" } }) as any;
    saveActivityDraft("post", "alice", 0, { form: {} });
    uni.getAccountInfoSync = () => ({ miniProgram: { appId: "second" } }) as any;
    expect(readActivityDraft("post", "alice", 0)).toBeNull();
    uni.setStorageSync = () => { throw new Error("full"); };
    expect(saveActivityDraft("post", "alice", 0, {})).toBe(false);
  });
});
