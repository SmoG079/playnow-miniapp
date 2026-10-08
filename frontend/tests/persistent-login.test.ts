import { beforeEach, describe, expect, it, vi } from "vitest";

describe("persistent WeChat login", () => {
  const storage = new Map<string, string>();
  beforeEach(async () => {
    vi.resetModules(); storage.clear();
    vi.stubGlobal("uni", {
      getStorageSync: (key: string) => storage.get(key) || "",
      setStorageSync: (key: string, value: string) => storage.set(key, value),
      removeStorageSync: (key: string) => storage.delete(key),
      getAccountInfoSync: () => ({ miniProgram: { appId: "wxe6fd99528373b676" } }),
      request: vi.fn(), uploadFile: vi.fn(), login: vi.fn(), reLaunch: vi.fn(),
    });
    vi.stubGlobal("getCurrentPages", () => [{ route: "pages/profile/index" }]);
    const { sessionContext, SESSION_CONTEXT_KEY } = await import("../src/services/session-context");
    storage.set(SESSION_CONTEXT_KEY, sessionContext());
    storage.set("access_token", "expired"); storage.set("refresh_token", "expired-refresh");
  });
  function backend() {
    (uni as any).request = vi.fn((o: any) => {
      if (o.url.endsWith("/auth/refresh")) o.success({ statusCode: 401, data: { detail: "expired" } });
      else if (o.url.endsWith("/auth/login")) o.success({ statusCode: 200, data: { access_token: "restored", refresh_token: "restored-refresh" } });
      else if (o.header.Authorization === "Bearer restored") o.success({ statusCode: 200, data: { id: "wx-current" } });
      else o.success({ statusCode: 401, data: { detail: "expired" } });
    });
    (uni as any).uploadFile = vi.fn((o: any) => o.success(o.header.Authorization === "Bearer restored"
      ? { statusCode: 200, data: '{"url":"https://media.example/avatar.jpg"}' }
      : { statusCode: 401, data: '{"detail":"expired"}' }));
  }
  it("requests and uploads share one silent login after 30 days of inactivity", async () => {
    backend();
    let codeResponse: any;
    (uni as any).login = vi.fn((o: any) => { codeResponse = o.success; });
    const { request, uploadFile } = await import("../src/services/api");
    const a = request("/users/me"), b = uploadFile("wxfile://avatar.jpg");
    await vi.waitFor(() => expect(uni.login).toHaveBeenCalledOnce());
    codeResponse({ code: "fresh-wechat-code" });
    await expect(a).resolves.toEqual({ id: "wx-current" });
    await expect(b).resolves.toHaveProperty("url");
    expect(storage.get("refresh_token")).toBe("restored-refresh");
    expect(uni.reLaunch).not.toHaveBeenCalled();
    expect((uni.request as any).mock.calls.filter(([o]: any[]) => o.url.endsWith("/auth/login"))).toHaveLength(1);
  });
  it("temporary WeChat failure retains login and the next request can retry", async () => {
    backend();
    (uni as any).login = vi.fn((o: any) => o.fail({ errMsg: "offline" }));
    const { request } = await import("../src/services/api");
    await expect(request("/users/me")).rejects.toThrow("微信登录恢复失败");
    expect(storage.get("refresh_token")).toBe("expired-refresh");
    expect(uni.reLaunch).not.toHaveBeenCalled();
    (uni as any).login = vi.fn((o: any) => o.success({ code: "fresh" }));
    await expect(request("/users/me")).resolves.toHaveProperty("id", "wx-current");
  });
  it("logout during silent login cannot restore the account", async () => {
    backend(); let codeResponse: any;
    (uni as any).login = vi.fn((o: any) => { codeResponse = o.success; });
    const { request, clearTokens } = await import("../src/services/api");
    const pending = request("/users/me");
    await vi.waitFor(() => expect(uni.login).toHaveBeenCalledOnce());
    clearTokens(); codeResponse({ code: "late" });
    await expect(pending).rejects.toThrow("登录会话已变化");
    expect(storage.has("access_token")).toBe(false);
    expect((uni.request as any).mock.calls.some(([o]: any[]) => o.url.endsWith("/auth/login"))).toBe(false);
  });
  it("guests and a different AppID are never silently logged in", async () => {
    backend(); const { request, clearTokens } = await import("../src/services/api");
    storage.set("session_context", "account-v2:another-app:old-api");
    await expect(request("/users/me")).rejects.toThrow("expired");
    expect(uni.login).not.toHaveBeenCalled();
    clearTokens();
    await expect(request("/users/me")).rejects.toThrow("登录已失效");
    expect(uni.login).not.toHaveBeenCalled();
  });
});
