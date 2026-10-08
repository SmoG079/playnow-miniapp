import { beforeEach, describe, expect, it, vi } from "vitest";
import { saveTournamentDraft, readTournamentDraft, clearTournamentDraft } from "../src/services/tournament-draft";
import { returnToActivityForm } from "../src/utils/navigation";
describe("tournament form continuity", () => {
  const storage = new Map<string, any>();
  beforeEach(() => {
    storage.clear(); vi.useRealTimers();
    vi.stubGlobal("uni", {setStorageSync:(k:string,v:any)=>storage.set(k,v),getStorageSync:(k:string)=>storage.get(k),removeStorageSync:(k:string)=>storage.delete(k),navigateBack:vi.fn(),redirectTo:vi.fn(),switchTab:vi.fn()});
    vi.stubGlobal("getCurrentPages",()=>[{route:"pages/publish/tournament-create"},{route:"pages/booking/venue-detail"},{route:"pages/booking/confirm"}]);
  });
  it("booking confirmation returns to the original form instance", () => {
    returnToActivityForm("tournament");
    expect(uni.navigateBack).toHaveBeenCalledWith({delta:2});expect(uni.redirectTo).not.toHaveBeenCalled();
    vi.stubGlobal("getCurrentPages",()=>[{route:"pages/booking/confirm"}]);
    returnToActivityForm("tournament");expect(uni.redirectTo).toHaveBeenCalledWith({url:"/pages/publish/tournament-create"});
  });
  it("restores form, rules and cloud covers after page reconstruction", () => {
    const draft={form:{title:"保留的比赛",start_date:"2026-11-01",max_participants:16},config:{format:"round_robin"},images:["https://cos.example/cover.jpg"]};
    saveTournamentDraft("owner",0,draft);draft.form.title="later change";
    expect(readTournamentDraft("owner",0).form.title).toBe("保留的比赛");
    expect(readTournamentDraft("owner",0).images).toEqual(["https://cos.example/cover.jpg"]);
    expect(readTournamentDraft("another-account",0)).toBeNull();expect(readTournamentDraft("owner",2)).toBeNull();
  });
  it("draft cache expires and is cleared after successful creation", () => {
    vi.useFakeTimers();saveTournamentDraft("owner",0,{form:{title:"draft"}});
    vi.advanceTimersByTime(24*60*60*1000+1);expect(readTournamentDraft("owner",0)).toBeNull();
    saveTournamentDraft("owner",0,{form:{title:"draft"}});clearTournamentDraft();expect(readTournamentDraft("owner",0)).toBeNull();vi.useRealTimers();
  });
});
