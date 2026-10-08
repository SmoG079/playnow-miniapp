import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
const request = vi.hoisted(() => vi.fn());
vi.mock("../src/services/api", () => ({ request }));
import { useDiscovery } from "../src/stores/discovery";

describe("shared city preference", () => {
  const storage = new Map<string, any>();
  let getLocation: any;
  beforeEach(() => {
    storage.clear(); request.mockReset();
    getLocation = vi.fn((options: any) => options.success({ latitude: 32, longitude: 119 }));
    vi.stubGlobal("uni", {
      getStorageSync: (key: string) => storage.get(key),
      setStorageSync: (key: string, value: any) => storage.set(key, value),
      getLocation,
    });
    setActivePinia(createPinia());
  });
  it("shares one initial request and reuses the city across pages and reopening", async () => {
    request.mockResolvedValue({ province: "江苏省", city: "扬州市", district: "广陵区" });
    const city = useDiscovery();
    await Promise.all([city.ensureCity(), city.ensureCity(), city.ensureCity()]);
    await city.ensureCity();
    expect(getLocation).toHaveBeenCalledTimes(1); expect(request).toHaveBeenCalledTimes(1);
    expect(useDiscovery().city).toBe("扬州市");
    setActivePinia(createPinia());
    const reopened = useDiscovery(); await reopened.ensureCity();
    expect(reopened.city).toBe("扬州市"); expect(getLocation).toHaveBeenCalledTimes(1);
    expect(reopened.latitude).toBeNull();
  });
  it("manual city selection wins over an older positioning response", async () => {
    let respond: any;
    request.mockReturnValue(new Promise(resolve => { respond = resolve; }));
    const city = useDiscovery(); const locating = city.locate();
    await Promise.resolve();
    city.selectRegion(["北京市", "市辖区", "朝阳区"]);
    respond({ city: "扬州市" });
    await expect(locating).rejects.toThrow("城市已变更");
    expect(city.city).toBe("北京市");
    setActivePinia(createPinia()); expect(useDiscovery().city).toBe("北京市");
  });
  it("map changes update the shared city; failed resolution cannot commit a wrong city", async () => {
    const city = useDiscovery(); city.selectRegion(["江苏省", "扬州市", "广陵区"]);
    request.mockRejectedValueOnce(new Error("quota"));
    await expect(city.selectPoint({ latitude: 31, longitude: 118 })).rejects.toThrow("quota");
    expect(city.city).toBe("扬州市"); expect(city.latitude).toBeNull();
    request.mockResolvedValue({ province: "江苏省", city: "南京市", district: "玄武区" });
    await city.selectPoint({ latitude: 32, longitude: 118 });
    expect(city.city).toBe("南京市"); expect(city.longitude).toBe(118);
    setActivePinia(createPinia()); expect(useDiscovery().city).toBe("南京市");
  });
  it("explicit relocation updates a cached city", async () => {
    const city = useDiscovery(); city.selectRegion(["江苏省", "扬州市", "广陵区"]);
    await city.ensureCity(); expect(getLocation).not.toHaveBeenCalled();
    request.mockResolvedValue({ city: "南京市" }); await city.locate();
    expect(city.city).toBe("南京市");
  });
});
