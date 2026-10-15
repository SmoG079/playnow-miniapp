import { request } from "./api";
declare const wx: { env: { USER_DATA_PATH: string } };
export type ShareKind = "post" | "tournament";
export function sharedActivityId(query?: Record<string, any>): string {
  let value = String(query?.id || "");
  if (!value && query?.scene) {
    try { value = decodeURIComponent(String(query.scene)); } catch { return ""; }
  }
  return /^[1-9]\d*$/.test(value) ? value : "";
}
export async function activityCode(kind: ShareKind, id: string | number) {
  const code = await request<{image_base64:string;mime_type:string}>(`/sharing/${kind}/${id}/code`);
  const path = `${wx.env.USER_DATA_PATH}/playnow-${kind}-${id}.${code.mime_type === "image/png" ? "png" : "jpg"}`;
  await new Promise<void>((resolve,reject) => uni.getFileSystemManager().writeFile({filePath:path,data:code.image_base64,encoding:"base64",success:()=>resolve(),fail:()=>reject(new Error("小程序码保存失败，请重试"))}));
  return path;
}
export async function copyActivityLink(kind: ShareKind, id: string | number) {
  const result = await request<{url:string}>(`/sharing/${kind}/${id}/link`);
  await new Promise<void>((resolve,reject)=>uni.setClipboardData({data:result.url,success:()=>resolve(),fail:()=>reject(new Error("链接复制失败，请重试"))}));
}
