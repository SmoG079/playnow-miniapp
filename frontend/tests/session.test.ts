import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

describe("session token state", () => {
  const storage = new Map<string, string>();

  beforeEach(() => {
    storage.clear();
    vi.resetModules();
    vi.stubGlobal("uni", {
      getStorageSync: (key: string) => storage.get(key) || "",
      setStorageSync: (key: string, value: string) => storage.set(key, value),
      removeStorageSync: (key: string) => storage.delete(key),
      reLaunch: vi.fn(),
      navigateTo: vi.fn(),
      showToast: vi.fn(),
    });
    setActivePinia(createPinia());
  });

  it("登录写入令牌后立即更新登录状态", async () => {
    const { useSession } = await import("../src/stores/session");
    const session = useSession();

    expect(session.loggedIn).toBe(false);
    session.setTokens("access", "refresh");

    expect(session.loggedIn).toBe(true);
    expect(storage.get("access_token")).toBe("access");
    expect(storage.get("refresh_token")).toBe("refresh");
  });

  it("退出后同步清空令牌与登录状态", async () => {
    const { useSession } = await import("../src/stores/session");
    const session = useSession();
    session.setTokens("access", "refresh");

    session.logout();

    expect(session.loggedIn).toBe(false);
    expect(storage.has("access_token")).toBe(false);
    expect(storage.has("refresh_token")).toBe(false);
  });
  it("登录和退出时清理旧账号的业务暂存及用户权限", async () => {
    const { useSession } = await import("../src/stores/session");
    const session = useSession();
    session.user = { id: 1, role: "platform_admin" };
    storage.set("registered_post_ids", "旧列表");
    storage.set("booking_return", "旧预约");
    session.setTokens("new-access", "new-refresh");
    expect(session.user).toBeNull();
    expect(storage.has("registered_post_ids")).toBe(false);
    expect(storage.has("booking_return")).toBe(false);
    storage.set("booking_return", "待返回预约");
    session.logout();
    expect(storage.has("booking_return")).toBe(false);
  });
  it("退出后到达的个人资料响应不能恢复旧用户", async () => {
    let respond: any;
    (uni as any).request = vi.fn((options: any) => { respond = options.success; });
    const { useSession } = await import("../src/stores/session");
    const session = useSession();
    session.setTokens("access", "refresh");
    const pending = session.fetchUser();
    session.logout();
    respond({ statusCode: 200, data: { id: 1, role: "platform_admin" } });
    await pending;
    expect(session.user).toBeNull();
    expect(session.loggedIn).toBe(false);
  });
  it("退出后到达的刷新令牌响应不能恢复登录", async () => {
    let refreshResponse: any;
    (uni as any).request = vi.fn((options: any) => {
      if (options.url.endsWith("/auth/refresh")) refreshResponse = options.success;
      else options.success({ statusCode: 401, data: { detail: "expired" } });
    });
    const { useSession } = await import("../src/stores/session");
    const { request } = await import("../src/services/api");
    const session = useSession();
    session.setTokens("access", "refresh");
    const pending = request("/users/me");
    await Promise.resolve();
    session.logout();
    refreshResponse({ statusCode: 200, data: { access_token: "late", refresh_token: "late" } });
    await expect(pending).rejects.toThrow("登录会话已变化");
    expect(storage.has("access_token")).toBe(false);
    expect(session.user).toBeNull();
  });
  it.each([
    ["user", [], false, false],
    ["user", [7], false, false],
    ["club_admin", [], false, false],
    ["club_admin", [7], true, true],
    ["platform_admin", [], true, true],
  ])(
    "%s 的赛事入口和俱乐部权限一致 (%j)",
    async (role, ids, allowed, canManage) => {
      const { useSession } = await import("../src/stores/session");
      const session = useSession();
      session.setTokens("access", "refresh");
      session.user = {
        id: 1,
        role: String(role),
        managed_club_ids: ids as number[],
      };
      expect(session.canPublishTournament).toBe(allowed);
      expect(session.canManageClub(7)).toBe(canManage);
      expect(session.canManageClub(8)).toBe(role === "platform_admin");
      session.logout();
      expect(session.canPublishTournament).toBe(false);
    },
  );
});
