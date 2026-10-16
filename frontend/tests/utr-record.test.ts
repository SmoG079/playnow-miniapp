import { describe, expect, it } from "vitest";
import { utrValue, utrRank, UTR_SOURCE_NOTE } from "../src/services/utr-record";
describe("UTR record values", () => {
  it("preserves real zeros and leaves unsynced values empty", () => {
    expect(utrValue(0)).toBe("0"); expect(utrValue(0, 2)).toBe("0.00");
    for (const value of [null, undefined, "", NaN, -1, "invalid"]) expect(utrValue(value)).toBe("—");
  });
  it("formats independent stored UTR and NTRP values rather than converting them", () => {
    expect(utrValue(3.4, 2)).toBe("3.40");
    expect(utrValue("5.0", 1)).toBe("5.0");
    expect(utrRank(329791)).toBe("329,791");
    expect(utrRank(null)).toBe("—");
    expect(UTR_SOURCE_NOTE).toContain("所在年龄段");
    expect(UTR_SOURCE_NOTE).toContain("不能严格代表真实水平差异");
  });
});
