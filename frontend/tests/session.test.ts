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
});
