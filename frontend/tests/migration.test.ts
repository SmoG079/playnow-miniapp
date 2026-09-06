import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(__dirname, "..");

describe("production migration", () => {
  it("registers and implements the same 30 routes as the native app", () => {
    const migrated = JSON.parse(
      fs.readFileSync(path.join(root, "src/pages.json"), "utf8"),
    ).pages.map((x: any) => x.path);
    const native = JSON.parse(
      fs.readFileSync(path.join(root, "../miniprogram/app.json"), "utf8"),
    ).pages;
    expect(migrated).toEqual(native);
    for (const route of migrated)
      expect(fs.existsSync(path.join(root, `src/${route}.vue`)), route).toBe(
        true,
      );
  });

  it("contains no runtime dependency on prototype fixtures", () => {
    const source = fs
      .readdirSync(path.join(root, "src/pages"), { recursive: true })
      .filter((file) => String(file).endsWith(".vue"))
      .map((file) =>
        fs.readFileSync(path.join(root, "src/pages", String(file)), "utf8"),
      )
      .join("\n");
    expect(source).not.toMatch(/fixtures|usePrototype|模拟预约|示例数据/);
  });
});
