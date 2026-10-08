import { uploadFile } from "./api";

/** WeChat simulator file URLs look like HTTP URLs but are not uploaded media. */
export function isRemoteImage(path: string): boolean {
  if (!/^https?:\/\//i.test(path)) return false;
  return !/^https?:\/\/(?:tmp|usr)(?:[/:]|$)/i.test(path)
    && !/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/__tmp__\//i.test(path);
}

export async function uploadedImage(path: string, type = "post"): Promise<string> {
  if (isRemoteImage(path)) return path;
  const result = await uploadFile(path, type);
  if (!isRemoteImage(result.url)) throw new Error("上传未返回有效图片地址");
  return result.url;
}

/** Upload before adding a preview; never render a simulator temporary file URL. */
export async function chooseUploadedImages(count: number, type: string, add: (url: string) => void): Promise<void> {
  if (count <= 0) return;
  let selected: UniApp.ChooseImageSuccessCallbackResult;
  try { selected = await uni.chooseImage({ count, sizeType: ["compressed"] }); }
  catch (error: any) {
    if (error?.errMsg?.includes("cancel")) return;
    throw error;
  }
  for (const path of selected.tempFilePaths) add(await uploadedImage(path, type));
}
