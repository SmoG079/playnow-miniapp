import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(resolve(__dirname, "..", "src", path), "utf8");

describe("club avatar", () => {
  it("prefers the uploaded logo over the cover in club listings", () => {
    expect(read("components/BookingClubList.vue")).toContain('c.logo_image || c.cover_image');
  });

  it("falls back to club_avatar on activity detail for backends that only send that field", () => {
    expect(read("pages/common/tournament-detail.vue")).toContain("t.club_logo || t.club_avatar");
    expect(read("pages/common/post-detail.vue")).toContain("post.club_logo || post.club_avatar");
  });

  it("shows the logo on the admin review list", () => {
    expect(read("pages/admin/club-manage.vue")).toContain('c.logo_image || c.cover_image');
  });
});
