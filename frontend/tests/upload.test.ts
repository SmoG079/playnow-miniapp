import { beforeEach, describe, expect, it, vi } from "vitest";

describe("authenticated uploads", () => {
  const storage = new Map<string, string>();
  beforeEach(() => {
    vi.resetModules(); storage.clear(); storage.set("access_token", "expired"); storage.set("refresh_token", "refresh");
    vi.stubGlobal("uni", {
      getStorageSync: (key: string) => storage.get(key) || "",
      setStorageSync: (key: string, value: string) => storage.set(key, value),
      removeStorageSync: (key: string) => storage.delete(key),
      request: vi.fn(), uploadFile: vi.fn(), reLaunch: vi.fn(),
    });
    vi.stubGlobal("getCurrentPages", () => [{ route: "pages/profile/edit" }]);
  });
  it("concurrent uploads share one refresh and retry with the new token", async () => {
    let respond: any;
    (uni as any).request = vi.fn((o: any) => { respond = o.success; });
    (uni as any).uploadFile = vi.fn((o: any) => {
      if (o.header.Authorization === "Bearer expired") o.success({ statusCode: 401, data: '{"detail":"expired"}' });
      else o.success({ statusCode: 200, data: '{"url":"https://media.example.com/avatar.jpg"}' });
    });
    const { uploadFile } = await import("../src/services/api");
    const a = uploadFile("wxfile://tmp/a.jpg", "avatar"), b = uploadFile("wxfile://tmp/b.jpg", "avatar");
    await Promise.resolve();
    expect(uni.request).toHaveBeenCalledTimes(1);
    respond({ statusCode: 200, data: { access_token: "new", refresh_token: "new-refresh" } });
    expect(await Promise.all([a,b])).toHaveLength(2);
    expect(uni.uploadFile).toHaveBeenCalledTimes(4);
  });
  it("expired refresh sends the user to login instead of hiding the 401", async () => {
    (uni as any).uploadFile = vi.fn((o: any) => o.success({ statusCode: 401, data: '{"detail":"expired"}' }));
    (uni as any).request = vi.fn((o: any) => o.success({ statusCode: 401, data: { detail: "expired refresh" } }));
    const { uploadFile } = await import("../src/services/api");
    await expect(uploadFile("wxfile://tmp/a.jpg")).rejects.toThrow("expired refresh");
    expect(storage.has("access_token")).toBe(false);
    expect(uni.reLaunch).toHaveBeenCalledOnce();
  });
  it("reports WeChat upload-domain restrictions separately from server rejection", async () => {
    (uni as any).uploadFile = vi.fn((o: any) => o.fail({ errMsg: "uploadFile:fail url not in domain list" }));
    const { uploadFile } = await import("../src/services/api");
    await expect(uploadFile("wxfile://tmp/a.jpg")).rejects.toThrow("上传域名未配置");
    (uni as any).uploadFile = vi.fn((o: any) => o.success({ statusCode: 413, data: '{"detail":"图片不能超过 5MB"}' }));
    await expect(uploadFile("wxfile://tmp/a.jpg")).rejects.toThrow("图片不能超过 5MB");
  });
});
