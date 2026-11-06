import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

describe("paused court commerce routes", () => {
  it.each(["confirm", "select", "venue-detail"])("old %s links cannot start booking work", route => {
    const page = fs.readFileSync(new URL(`../src/pages/booking/${route}.vue`, import.meta.url), "utf8");
    expect(page).toContain("<BookingUnavailable");
    const shared = fs.readFileSync(new URL("../src/components/BookingUnavailable.vue", import.meta.url), "utf8");
    const source = [...(page + shared).matchAll(/<script setup lang="ts">([\s\S]*?)<\/script>/g)].map(match => match[1].replace(/^import[\s\S]*?;\s*/gm, "")).join("\n");
    const request = vi.fn(() => { throw new Error("Paused route must not request slots or create an order"); });
    const payBooking = vi.fn(() => { throw new Error("Paused route must not initiate payment"); });
    const onLoad = vi.fn(), onShow = vi.fn();
    vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText, {request,payBooking,onLoad,onShow});
    expect(request).not.toHaveBeenCalled(); expect(payBooking).not.toHaveBeenCalled();
    expect(onLoad).not.toHaveBeenCalled(); expect(onShow).not.toHaveBeenCalled();
    expect(shared).toContain("订场服务暂未开放");
    expect(shared).toContain("/pages/booking/club-list");
  });
});
