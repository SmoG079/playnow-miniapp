import { beforeEach, describe, expect, it, vi } from "vitest";
const request = vi.hoisted(() => vi.fn());
vi.mock("../src/services/api", () => ({ request }));
import { loadRatingQuestionnaire, saveRatingAssessment } from "../src/services/rating-assessment";

describe("NTRP self assessment API", () => {
  beforeEach(() => { request.mockReset(); });
  it("loads versioned questions and submits answers without client rating or UTR values", async () => {
    const catalog = { version: "playnow_self_v1", questions: [], quick_levels: [] };
    request.mockResolvedValueOnce(catalog);
    expect(await loadRatingQuestionnaire()).toBe(catalog);
    expect(request).toHaveBeenCalledWith("/users/me/rating-questionnaire");
    request.mockResolvedValueOnce({ ntrp_level: 4, rating_source: "self_assessment" });
    expect(await saveRatingAssessment(catalog.version, "quick", { level: 4 })).toEqual({ ntrp_level: 4, rating_source: "self_assessment" });
    expect(request).toHaveBeenLastCalledWith("/users/me/rating-assessment", {
      method: "POST", data: { version: catalog.version, mode: "quick", answers: { level: 4 } },
    });
  });
  it("propagates save failures so the popup retains its answers for retry", async () => {
    request.mockRejectedValue(new Error("network unavailable"));
    await expect(saveRatingAssessment("playnow_self_v1", "full", { rally: 3 })).rejects.toThrow("network unavailable");
  });
});
