import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

describe("paused court commerce routes", () => {
  it.each(["confirm", "select", "venue-detail"])("old %s links cannot start booking work", route => {
    const page = fs.readFileSync(new URL(`../src/pages/booking/${route}.vue`, import.meta.url), "utf8");
    const source = page.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1].replace(/^import[\s\S]*?;\s*/gm, "");
    const request = vi.fn(() => { throw new Error("Paused route must not request slots or create an order"); });
    const payBooking = vi.fn(() => { throw new Error("Paused route must not initiate payment"); });
    const onLoad = vi.fn(), onShow = vi.fn();
    vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText, {request,payBooking,onLoad,onShow});
    expect(request).not.toHaveBeenCalled(); expect(payBooking).not.toHaveBeenCalled();
    expect(onLoad).not.toHaveBeenCalled(); expect(onShow).not.toHaveBeenCalled();
    expect(page).toContain("订场服务暂未开放");
    expect(page).toContain("/pages/booking/club-list");
  });
});
