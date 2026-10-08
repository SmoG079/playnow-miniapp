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

/** Native image picker; compressed images reduce memory pressure on real devices. */
export async function chooseImagePaths(count: number): Promise<string[]> {
  if (typeof uni.chooseMedia === "function") {
    const selected = await new Promise<UniApp.ChooseMediaSuccessCallbackResult>((resolve,reject) => uni.chooseMedia({
      count, mediaType:["image"], sizeType:["compressed"], sourceType:["album","camera"], success:resolve, fail:reject,
    }));
    return (selected.tempFiles || []).map(file => file.tempFilePath).filter(Boolean);
  }
  const selected = await uni.chooseImage({count,sizeType:["compressed"],sourceType:["album","camera"]});
  const paths = selected.tempFilePaths;
  return Array.isArray(paths) ? paths : paths ? [paths] : [];
}

/** Upload before adding a preview; never render a simulator temporary file URL. */
export async function chooseUploadedImages(count: number, type: string, add: (url: string) => void): Promise<void> {
  if (count <= 0) return;
  let paths: string[];
  try { paths = await chooseImagePaths(count); }
  catch (error: any) {
    if (error?.errMsg?.includes("cancel")) return;
    throw error;
  }
  for (const path of paths) add(await uploadedImage(path, type));
}
