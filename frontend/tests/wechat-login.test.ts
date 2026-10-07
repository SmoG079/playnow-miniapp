import { describe, expect, it } from "vitest";
import project from "../src/project.wx.json";
import { assertWeChatAppId, WECHAT_APP_ID } from "../src/services/wechat-login";

describe("微信登录 AppID 校验", () => {
  it("构建配置与登录校验使用同一个 AppID", () => {
    expect(project.appid).toBe(WECHAT_APP_ID);
  });
  it("允许源码配置对应的小程序登录", () => {
    expect(() => assertWeChatAppId(WECHAT_APP_ID)).not.toThrow();
  });
  it("拦截另一小程序的凭证，避免提交给当前后端", () => {
    expect(() => assertWeChatAppId("wxfad430ba15c6c3e2")).toThrow(
      "小程序 AppID 与项目配置不一致",
    );
  });
});
