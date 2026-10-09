import { request } from "./api";

export interface RatingQuestionnaire {
  version: string;
  notice: string;
  quick_levels: { value: number; name: string; description: string }[];
  questions: { id: string; title: string; options: { value: number; description: string }[] }[];
}
export interface RatingResult { ntrp_level: number; rating_source: "self_assessment" }

export function loadRatingQuestionnaire() {
  return request<RatingQuestionnaire>("/users/me/rating-questionnaire");
}
export function saveRatingAssessment(version: string, mode: "quick" | "full", answers: Record<string, number>) {
  return request<RatingResult>("/users/me/rating-assessment", {
    method: "POST", data: { version, mode, answers },
  });
}
