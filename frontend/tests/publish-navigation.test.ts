import { afterEach, describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { openPage, returnToActivityForm } from "../src/utils/navigation";
import { TAB_PAGES } from "../src/config";
import { activitySchedule, freshActivitySchedule, businessDate } from "../src/utils/date";

const pages = JSON.parse(fs.readFileSync(new URL("../src/pages.json", import.meta.url), "utf8"));
const tabModule = { exports: [] as any[] };
vm.runInNewContext(fs.readFileSync(new URL("../src/custom-tab-bar/tabs.js", import.meta.url), "utf8"), { module: tabModule });
const tabs = tabModule.exports;
afterEach(() => vi.unstubAllGlobals());

describe("publish hub and booking return navigation", () => {
  it("opens the hub as a tab and the post form as a separate page", () => {
    vi.stubGlobal("uni", { switchTab: vi.fn(), navigateTo: vi.fn() });
    expect(pages.tabBar.list[2].pagePath).toBe("pages/publish/index");
    expect(TAB_PAGES).toContain("/pages/publish/index");
    expect(TAB_PAGES).not.toContain("/pages/publish/post-create");
    openPage("/pages/publish/index");
    openPage("/pages/publish/post-create");
    expect(uni.switchTab).toHaveBeenCalledWith({ url: "/pages/publish/index" });
    expect(uni.navigateTo).toHaveBeenCalledWith({ url: "/pages/publish/post-create" });
  });
  it("returns a paid booking to the existing post form", () => {
    vi.stubGlobal("getCurrentPages", () => [{ route: "pages/publish/index" }, { route: "pages/publish/post-create" }, { route: "pages/booking/select" }, { route: "pages/booking/confirm" }]);
    vi.stubGlobal("uni", { navigateBack: vi.fn() });
    returnToActivityForm("post");
    expect(uni.navigateBack).toHaveBeenCalledWith({ delta: 2 });
  });
  it("opens the post form directly when its previous page is unavailable", () => {
    vi.stubGlobal("getCurrentPages", () => [{ route: "pages/booking/confirm" }]);
    vi.stubGlobal("uni", { redirectTo: vi.fn() });
    returnToActivityForm("post");
    expect(uni.redirectTo).toHaveBeenCalledWith({ url: "/pages/publish/post-create" });
  });
});

function customTabbar(route = "pages/home/index", count = 0, token = "test-token") {
  let definition: any;
  const wx = { getStorageSync: () => token, navigateTo: vi.fn(), nextTick: (fn: () => void) => fn(), getWindowInfo: () => ({ screenHeight: 844, safeArea: { bottom: 810 } }), switchTab: vi.fn((options: any) => { route = options.url.slice(1); options.success?.(); }) };
  const app = {globalData:{playnowUnread:count}};
  vm.runInNewContext(fs.readFileSync(new URL("../src/custom-tab-bar/index.js", import.meta.url), "utf8"), {
    require: (name: string) => { if (name !== "./tabs.js") throw new Error("Unsupported native module"); return tabs; }, Component: (value: any) => { definition = value; },
    getCurrentPages: () => [{ route }], getApp: () => app, wx,
  });
  const instance = { data: { ...definition.data }, ...definition.methods, setData(value: any) { Object.assign(this.data, value); } };
  definition.lifetimes.attached.call(instance);
  return { definition, instance, wx, setRoute: (value: string) => { route = value; } };
}

describe("WeChat raised publish tab", () => {
  it("keeps all five routes and icons aligned with the app configuration", () => {
    expect(tabs).toEqual(pages.tabBar.list);
    expect(tabs).toHaveLength(5);
  });
  it.each([2, 4])("opens logged-in tab %s and updates selection after navigation succeeds", index => {
    const { instance, wx } = customTabbar();
    instance.switchTab({ currentTarget: { dataset: { index } } });
    expect(wx.switchTab).toHaveBeenCalledWith(expect.objectContaining({ url: "/" + tabs[index].pagePath }));
    expect(instance.data.selected).toBe(index);
  });
  it.each([2, 4])("opens login directly for guest tab %s and keeps the original tab selected", index => {
    const { instance, wx } = customTabbar("pages/home/index", 0, "");
    instance.switchTab({ currentTarget: { dataset: { index } } });
    expect(wx.navigateTo).toHaveBeenCalledWith({ url: "/pages/common/login?redirect=" + encodeURIComponent("/" + tabs[index].pagePath) });
    expect(wx.switchTab).not.toHaveBeenCalled();
    expect(instance.data.selected).toBe(0);
  });
  it("restores the correct selection on page show and preserves unread badges", () => {
    const { definition, instance, setRoute } = customTabbar("pages/profile/index", 123);
    expect(instance.data.selected).toBe(4);
    expect(instance.data.unread).toBe("99+");
    expect(instance.data.safeBottom).toBe(34);
    setRoute("pages/chat/index");
    definition.pageLifetimes.show.call(instance);
    expect(instance.data.selected).toBe(3);
  });
});

const formSource = fs.readFileSync(new URL("../src/pages/publish/post-create.vue", import.meta.url), "utf8")
  .match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1]
  .replace(/^import[\s\S]*?;\s*/gm, "");
async function restorePostForm(booking: any = null) {
  let show: () => Promise<void> = async () => {};
  const uni = { getStorageSync: () => booking, removeStorageSync: vi.fn() };
  const context: any = {
    ref: (value: any) => ({ value }), reactive: (value: any) => value, watch: () => {},
    onShow: (fn: any) => { show = fn; }, onHide: () => {}, onUnload: () => {},
    useSession: () => ({ user: { id: "alice" }, requireLogin: () => true, fetchUser: async () => {} }),
    useDiscovery: () => ({ city: "扬州市", ensureCity: async () => {} }), businessDate: () => "2026-10-15",
    activitySchedule, freshActivitySchedule,
    readActivityDraft: () => ({ form: { title: "已保存的约球", preferred_date: "2020-10-14", preferred_start: "19:00", preferred_end: "21:00" }, images: [] }),
    saveActivityDraft: vi.fn(), request: async () => ({ id: 1 }), uni,
  };
  vm.createContext(context);
  vm.runInContext(ts.transpileModule(formSource, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText +
    ";globalThis.reviewForm = form; globalThis.reviewReady = draftReady;", context);
  await show();
  return { context, uni };
}
it("keeps the saved draft when entering the separate post form", async () => {
  const { context } = await restorePostForm();
  expect(context.reviewForm.title).toBe("已保存的约球");
  expect(context.reviewForm.preferred_date).toBe(businessDate());
  expect(context.reviewReady.value).toBe(true);
});
it("applies the booking return to that form and consumes it once", async () => {
  const { context, uni } = await restorePostForm({ club_id: 1, booking_id: 7, venue_id: 2, slot_date: "2026-10-15", slot_start: "10:00:00", slot_end: "11:00:00" });
  expect(context.reviewForm.booking_id).toBe(7);
  expect(context.reviewForm.preferred_start).toBe("10:00");
  expect(uni.removeStorageSync).toHaveBeenCalledWith("booking_return");
});

function showGatedTab(loggedIn: boolean, page: string) {
  let show: () => void = () => {};
  const session = { loggedIn, syncTokens: vi.fn(), fetchUser: vi.fn(async () => {}) };
  const uni = { redirectTo: vi.fn() };
  const source = fs.readFileSync(new URL(`../src/pages/${page}/index.vue`, import.meta.url), "utf8")
    .match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1].replace(/^import[\s\S]*?;\s*/gm, "");
  const context: any = { computed: (fn: any) => ({ get value() { return fn(); } }), identityLabels: () => [], ref: (value: any) => ({ value }), onShow: (fn: any) => { show = fn; }, useSession: () => session, uni };
  vm.createContext(context);
  vm.runInContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText +
    ";globalThis.allowedState = allowed;", context);
  show();
  return { session, uni, allowed: context.allowedState.value };
}
it.each(["publish", "profile"])("redirects direct guest visits to %s without displaying the page", page => {
  const { session, uni, allowed } = showGatedTab(false, page);
  expect(allowed).toBe(false);
  expect(session.syncTokens).toHaveBeenCalled();
  expect(session.fetchUser).not.toHaveBeenCalled();
  expect(uni.redirectTo).toHaveBeenCalledWith({ url: "/pages/common/login?redirect=" + encodeURIComponent(`/pages/${page}/index`) });
});
it.each(["publish", "profile"])("shows %s for logged-in users", page => {
  const { session, uni, allowed } = showGatedTab(true, page);
  expect(allowed).toBe(true);
  expect(session.fetchUser).toHaveBeenCalled();
  expect(uni.redirectTo).not.toHaveBeenCalled();
});
