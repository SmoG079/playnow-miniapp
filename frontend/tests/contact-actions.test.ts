import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const read = (path: string) => readFileSync(resolve(__dirname, "..", path), "utf8");
const contact = read("src/components/ContactActions.vue");
const tournament = read("src/pages/common/tournament-detail.vue");
const post = read("src/pages/common/post-detail.vue");

describe("contact actions", () => {
  it("uses icon-only round buttons so rows stay compact", () => {
    expect(contact).toContain('name="message"');
    expect(contact).toContain('name="phone"');
    expect(contact).not.toContain("contact-label");
    expect(contact).toContain("border-radius: 50%");
  });

  it("keeps an accessible name for both icon buttons", () => {
    expect(contact).toContain("私聊主办方");
    expect(contact).toContain("私聊该球友");
    expect(contact).toContain('aria-label="拨打电话"');
  });

  it("reaches the organiser without needing their public id", () => {
    // The chat button stays visible for the host, and target_user_id is only
    // sent when a specific player is addressed — the backend falls back to the
    // organiser otherwise.
    expect(contact).toMatch(/v-if="userId \|\| organizer"/);
    expect(contact).toContain('if (props.userId) data.target_user_id = props.userId;');
  });

  it("sits under the admission badge instead of the action row", () => {
    expect(tournament).toMatch(/registration-side[\s\S]{0,200}?registration-badge[\s\S]{0,220}?<ContactActions/);
    expect(tournament).toMatch(/\.registration-side\{[^}]*flex-direction:column/);
  });

  it("shows both buttons on the organiser card of a tournament", () => {
    expect(tournament).toMatch(/<ContactActions\s+v-if="!viewerIsOrganizer"\s+organizer/);
    expect(tournament).toContain('t.organizer_phone || (t.club_id ? t.contact_phone : null)');
  });

  it("falls back to the public user id older backends already return", () => {
    // `user_public_id` only exists after the backend deploy; `user_id` is the
    // public id on the currently deployed build, so the chat button keeps
    // working in between.
    expect(tournament).toMatch(/function registrationContactId[\s\S]{0,200}?r\.user_public_id[\s\S]{0,200}?r\.user_id/);
    expect(tournament).toMatch(/typeof current\.organizer_user_id === "string"/);
  });

  it("shows both buttons on the host card of a post", () => {
    expect(post).toMatch(/<ContactActions[\s\S]{0,200}?phone="post\.user_phone/);
  });
});
