import { listAll } from "./api";

// Each list comes from the authenticated server; one failure must not hide the other.
export async function loadPersonalRecords() {
  const [tournaments, posts] = await Promise.allSettled([
    listAll<any>("/users/me/tournaments"),
    listAll<any>("/users/me/post-registrations"),
  ]);
  return { tournaments, posts };
}
