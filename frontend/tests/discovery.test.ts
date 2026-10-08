import { describe, it, expect } from "vitest";
import { regionCity } from "../src/stores/discovery";
import { discoveryQuery, ownLevel } from "../src/services/discovery";
describe("city discovery", () => {
  it("manual city selection handles municipalities and provincial counties", () => {
    expect(regionCity(["江苏省", "扬州市", "广陵区"])).toBe("扬州市");
    expect(regionCity(["北京市", "市辖区", "朝阳区"])).toBe("北京市");
    expect(regionCity(["河南省", "省直辖县级行政区划", "济源市"])).toBe("济源市");
  });
  it("queries keep city, day and distance together and reject an empty city", () => {
    expect(discoveryQuery("", "date_asc", "", null, null)).toBe("");
    const q = new URLSearchParams(discoveryQuery("扬州市", "distance", "2026-11-01", 32.4, 119.4));
    expect(q.get("city")).toBe("扬州市"); expect(q.get("on_date")).toBe("2026-11-01");
    expect(q.get("lat")).toBe("32.4"); expect(q.get("sort_by")).toBe("distance");
  });
  it("my level uses validated profile data", () => {
    expect(ownLevel("3.5")).toBe("3.5"); expect(ownLevel(null)).toBeNull();
    expect(ownLevel("3.2")).toBeNull(); expect(ownLevel(8)).toBeNull();
  });
});
