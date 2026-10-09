import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useWeather } from "../src/stores/weather";
import { request } from "../src/services/api";
vi.mock("../src/services/api", () => ({ request: vi.fn() }));
const data = (city: string, temperature = 25) => ({ city, temperature, observed_at: "2026-10-09 15:00", condition: "晴" });
beforeEach(() => { setActivePinia(createPinia()); vi.mocked(request).mockReset(); });
describe("city weather", () => {
  it("shares pending requests and cached weather between pages, including zero degrees", async () => {
    let done!: (value: any) => void;
    vi.mocked(request).mockImplementation(() => new Promise(resolve => { done = resolve; }));
    const store = useWeather();
    const first = store.refresh("扬州市", "江苏省"), second = store.refresh("扬州市", "江苏省");
    expect(request).toHaveBeenCalledTimes(1);
    done(data("扬州市", 0)); await Promise.all([first, second]);
    await store.refresh("扬州市", "江苏省");
    expect(store.current?.temperature).toBe(0); expect(store.loading).toBe(false);
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("does not let an old city response overwrite the new city", async () => {
    let done!: (value: any) => void;
    vi.mocked(request).mockImplementationOnce(() => new Promise(resolve => { done = resolve; })).mockResolvedValueOnce(data("南京市", 18));
    const store = useWeather(), old = store.refresh("扬州市");
    await store.refresh("南京市"); done(data("扬州市")); await old;
    expect(store.current?.city).toBe("南京市");
  });
  it("clears temperature on failure and delays repeated retries", async () => {
    const store = useWeather();
    vi.mocked(request).mockResolvedValueOnce(data("扬州市")).mockRejectedValueOnce(new Error("offline"));
    await store.refresh("扬州市"); await store.refresh("南京市"); await store.refresh("南京市");
    expect(store.current).toBeNull(); expect(store.loading).toBe(false); expect(request).toHaveBeenCalledTimes(2);
  });
  it("rejects malformed or mismatched temperatures and skips unselected cities", async () => {
    const store = useWeather(); await store.refresh(""); expect(request).not.toHaveBeenCalled();
    vi.mocked(request).mockResolvedValueOnce(data("其他城市")).mockResolvedValueOnce(data("南京市", NaN));
    await store.refresh("扬州市"); expect(store.current).toBeNull();
    await store.refresh("南京市"); expect(store.current).toBeNull();
  });
});
