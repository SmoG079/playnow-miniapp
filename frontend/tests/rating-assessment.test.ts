import { beforeEach, describe, expect, it, vi } from "vitest";
const request = vi.hoisted(() => vi.fn());
vi.mock("../src/services/api", () => ({ request }));
import { assessQuestionnaire, NTRP_QUESTIONS } from "../src/domain/rating-assessment";
import { saveRatingAssessment } from "../src/services/rating-assessment";

describe("local NTRP self assessment", () => {
  beforeEach(() => { request.mockReset(); });

  const answers = { experience: 4, forehand: 4.5, backhand: 2, serve: 4, return: 4, net: 4.5, tactics: 4.5 };

  it("caps the calibration example at the weakest score plus one", () => {
    const result = assessQuestionnaire(answers);
    expect(result).toMatchObject({ rating: 3, weakestScore: 2, weakestTitle: "反手", cap: 3, showWeaknessTip: true });
    expect(result?.average).toBeCloseTo(3.93);
  });

  it("rounds down and hides the weakness tip when the weakest score equals the result", () => {
    expect(assessQuestionnaire({ ...answers, backhand: 3.5, net: 3.5 })).toMatchObject({
      rating: 4, weakestScore: 3.5, weakestTitle: "反手", showWeaknessTip: true,
    });
    expect(assessQuestionnaire({ ...answers, forehand: 3.5, backhand: 3.5, net: 3.5, tactics: 3.5 })).toMatchObject({
      rating: 3.5, weakestScore: 3.5, weakestTitle: "正手", showWeaknessTip: false,
    });
  });

  it("requires a valid option for every question", () => {
    expect(assessQuestionnaire({ experience: 4 })).toBeNull();
    expect(assessQuestionnaire({ ...answers, backhand: 4 })).toBeNull();
    expect(assessQuestionnaire({ ...answers, serve: NaN })).toBeNull();
  });

  it("uses the supplied option scores", () => {
    expect(NTRP_QUESTIONS.map(question => question.options.map(option => option.score))).toEqual([
      [1, 2, 3, 4, 5], [1.5, 2, 3, 3.5, 4.5, 5.5], [1.5, 2, 2.5, 3.5, 4.5, 5.5],
      [1.5, 2, 3, 4, 5], [1.5, 2.5, 3, 4, 5], [2, 3, 3.5, 4.5, 5.5], [1, 2.5, 3.5, 4.5, 5.5],
    ]);
  });

  it("saves only the final level via the profile API", async () => {
    request.mockResolvedValueOnce({ msg: "ok" });
    await saveRatingAssessment(3);
    expect(request).toHaveBeenCalledWith("/users/me", {
      method: "PUT", data: { ntrp_level: 3 },
    });
  });

  it("propagates save failures so the popup retains its answers for retry", async () => {
    request.mockRejectedValue(new Error("network unavailable"));
    await expect(saveRatingAssessment(4)).rejects.toThrow("network unavailable");
  });
});
