import { beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("../src/services/api", () => ({ listAll: vi.fn() }));
import { listAll } from "../src/services/api";
import { loadPersonalRecords } from "../src/services/personal-records";

describe("数据库个人记录", () => {
  beforeEach(() => vi.resetAllMocks());
  it("不依赖本地存储，切换账号后重新查询两类记录", async () => {
    const mocked = vi.mocked(listAll);
    mocked.mockResolvedValueOnce([{ id: 1 }]).mockResolvedValueOnce([{ id: 2 }]);
    const first = await loadPersonalRecords();
    expect(first.posts).toEqual({ status: "fulfilled", value: [{ id: 2 }] });
    mocked.mockResolvedValueOnce([{ id: 3 }]).mockResolvedValueOnce([]);
    const second = await loadPersonalRecords();
    expect(second.tournaments).toEqual({ status: "fulfilled", value: [{ id: 3 }] });
    expect(second.posts).toEqual({ status: "fulfilled", value: [] });
    expect(mocked.mock.calls.map(([url]) => url)).toEqual([
      "/users/me/tournaments", "/users/me/post-registrations",
      "/users/me/tournaments", "/users/me/post-registrations",
    ]);
  });
  it.each(["tournaments", "posts"])("%s 请求失败不丢弃另一类记录", async (failed) => {
    vi.mocked(listAll).mockImplementation(async (url) => {
      if (url.endsWith(failed === "posts" ? "post-registrations" : "tournaments"))
        throw new Error("网络失败");
      return [{ id: 1 }];
    });
    const result = await loadPersonalRecords();
    expect(result[failed as "posts" | "tournaments"].status).toBe("rejected");
    expect(result[failed === "posts" ? "tournaments" : "posts"].status).toBe("fulfilled");
  });
});
