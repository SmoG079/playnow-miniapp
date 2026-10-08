import { describe, it, expect } from "vitest";
import { identityLabels, registrationLabel, activityQuery } from "../src/domain/my-activities";
describe("personal activity presentation", () => {
  it("shows concurrent admin identities without duplicate tags", () => {
    expect(identityLabels({role:"platform_admin",roles:["platform_admin","club_admin"],managed_club_ids:[1]})).toEqual(["系统管理员","俱乐部管理员"]);
    expect(identityLabels({role:"platform_admin"})).toEqual(["系统管理员"]);
    expect(identityLabels({role:"club_admin"})).toEqual(["俱乐部管理员"]);
    expect(identityLabels({role:"user"})).toEqual(["用户"]);
  });
  it("separates approval, capacity and payment instead of calling every applicant successful", () => {
    const base = {kind:"tournament",status:"open"};
    expect(registrationLabel({...base,registration:{approval:"pending",admission:"review"}})).toBe("待审核");
    expect(registrationLabel({...base,registration:{approval:"approved",admission:"waitlisted"}})).toBe("候补中");
    expect(registrationLabel({...base,registration:{approval:"approved",admission:"active",payment:"pending"}})).toBe("待支付");
    expect(registrationLabel({...base,registration:{approval:"approved",admission:"active",payment:"unverified"}})).toBe("付款待核验");
    expect(registrationLabel({...base,registration:{approval:"approved",admission:"active",payment:"none"}})).toBe("报名成功");
    expect(registrationLabel({...base,registration:{approval:"rejected",admission:"rejected"}})).toBe("未通过");
    expect(registrationLabel({...base,registration:{approval:"approved",admission:"expired"}})).toBe("名额已过期");
  });
  it("post reviews and closure remain visible in personal records", () => {
    expect(registrationLabel({kind:"post",status:"open",registration:{status:"pending"}})).toBe("待审核");
    expect(registrationLabel({kind:"post",status:"open",registration:{status:"rejected"}})).toBe("未通过");
    expect(registrationLabel({kind:"post",status:"closed",registration:{status:"pending"}})).toBe("活动已关闭");
  });
  it("search parameters preserve names and identifiers safely", () => {
    const query = new URLSearchParams(activityQuery("tournament","joined","review"," #123 & 杯赛 ",2).split("?")[1]);
    expect(query.get("kind")).toBe("tournament");expect(query.get("relation")).toBe("joined");expect(query.get("keyword")).toBe("#123 & 杯赛");expect(query.get("page")).toBe("2");
  });
});
