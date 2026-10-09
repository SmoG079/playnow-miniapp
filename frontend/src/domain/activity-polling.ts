import type { Tournament } from "../services/tournaments";

export function tournamentPollDelay(tournament: Pick<Tournament, "status" | "matches"> | null): number | null {
  if (!tournament) return 20_000;
  if (!["open", "ongoing"].includes(tournament.status)) return null;
  return tournament.matches.some(match => match.status === "pending" && match.team_a_id && match.team_b_id)
    ? 10_000 : 20_000;
}

export function activityPollDelay(items: any[]): number {
  const urgent = items.some(item => {
    if (["closed", "cancelled", "finished"].includes(item.status) || item.phase === "ended") return false;
    if (item.phase === "ongoing") return true;
    const registration = item.registration;
    if (!registration) return false;
    if (item.kind === "post") return registration.status === "pending";
    if (["cancelled", "expired", "rejected"].includes(registration.admission) || registration.approval === "rejected") return false;
    return registration.approval === "pending" || ["review", "waitlisted"].includes(registration.admission)
      || ["pending", "unverified", "abnormal"].includes(registration.payment);
  });
  return urgent ? 15_000 : 45_000;
}
