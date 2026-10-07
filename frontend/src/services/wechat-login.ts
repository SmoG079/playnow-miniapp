import manifest from "../manifest.json";

export const WECHAT_APP_ID = manifest["mp-weixin"].appid;

export function assertWeChatAppId(runtimeAppId: string) {
  if (runtimeAppId !== WECHAT_APP_ID) {
    throw new Error("小程序 AppID 与项目配置不一致，请重新导入项目");
  }
}
