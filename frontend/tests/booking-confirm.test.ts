import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * Court booking is paused. The placeholder screens used to stay reachable and
 * WeChat review rejected the mini program because of them, so they must not be
 * registered, shipped, or linked from anywhere.
 */
const retired = ["pages/booking/confirm", "pages/booking/select", "pages/booking/venue-detail"];

function walk(dir: string, out: string[] = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.(vue|ts|json)$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe("retired court booking routes", () => {
  it.each(retired)("%s is neither registered nor shipped", route => {
    const root = path.resolve(__dirname, "..");
    expect(fs.existsSync(path.join(root, `src/${route}.vue`)), route).toBe(false);
    const pages = JSON.parse(fs.readFileSync(path.join(root, "src/pages.json"), "utf8"));
    expect(pages.pages.map((page: any) => page.path)).not.toContain(route);
  });

  it("no source file links to a retired booking page", () => {
    const root = path.resolve(__dirname, "..");
    const offenders = walk(path.join(root, "src"))
      .filter(file => /booking[\\/](select|venue-detail|confirm)/.test(fs.readFileSync(file, "utf8")))
      .map(file => path.relative(root, file));
    expect(offenders).toEqual([]);
  });

  it("keeps the club list and booking history entry points", () => {
    const root = path.resolve(__dirname, "..");
    const pages = JSON.parse(fs.readFileSync(path.join(root, "src/pages.json"), "utf8"));
    const paths = pages.pages.map((page: any) => page.path);
    expect(paths).toContain("pages/booking/club-list");
    expect(paths).toContain("pages/profile/my-bookings");
    expect(pages.tabBar.list.map((item: any) => item.pagePath)).toContain("pages/booking/club-list");
  });
});
