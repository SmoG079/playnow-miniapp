import { request } from "./api";

export function saveRatingAssessment(level: number) {
  return request("/users/me", {
    method: "PUT", data: { ntrp_level: level },
  });
}
