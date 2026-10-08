import { beforeEach, describe, expect, it, vi } from "vitest";
const upload = vi.hoisted(() => vi.fn());
vi.mock("../src/services/api", () => ({ uploadFile: upload }));
import { isRemoteImage, uploadedImage, chooseUploadedImages } from "../src/services/media";

describe("image upload and previews", () => {
  beforeEach(() => { upload.mockReset(); vi.stubGlobal("uni", { chooseImage: vi.fn() }); });
  it("uploads simulator HTTP temporary files instead of persisting them as remote images", async () => {
    for (const path of ["http://tmp/cover.jpeg", "http://127.0.0.1:47692/__tmp__/cover.jpeg", "http://usr/avatar.png", "wxfile://tmp/photo.jpg"]) {
      expect(isRemoteImage(path)).toBe(false);
      upload.mockResolvedValueOnce({ url: "https://media.example.com/post/cover.jpg" });
      expect(await uploadedImage(path)).toBe("https://media.example.com/post/cover.jpg");
      expect(upload).toHaveBeenLastCalledWith(path, "post");
    }
    expect(await uploadedImage("https://media.example.com/existing.jpg")).toBe("https://media.example.com/existing.jpg");
    expect(upload).toHaveBeenCalledTimes(4);
  });
  it("shows only successful uploads and preserves them when a later upload fails", async () => {
    vi.mocked(uni.chooseImage).mockResolvedValue({ tempFilePaths: ["http://tmp/1.jpg", "http://tmp/2.jpg"] } as any);
    upload.mockResolvedValueOnce({ url: "https://media.example.com/1.jpg" }).mockRejectedValueOnce(new Error("upload failed"));
    const previews: string[] = [];
    await expect(chooseUploadedImages(2, "post", url => previews.push(url))).rejects.toThrow("upload failed");
    expect(previews).toEqual(["https://media.example.com/1.jpg"]);
  });
  it("cancellation makes no upload and invalid upload URLs never enter previews", async () => {
    vi.mocked(uni.chooseImage).mockRejectedValueOnce({ errMsg: "chooseImage:fail cancel" });
    const add=vi.fn();
    await chooseUploadedImages(1, "court", add);
    expect(upload).not.toHaveBeenCalled();
    vi.mocked(uni.chooseImage).mockResolvedValue({ tempFilePaths: ["http://tmp/1.jpg"] } as any);
    upload.mockResolvedValue({ url: "http://tmp/1.jpg" });
    await expect(chooseUploadedImages(1,"court",add)).rejects.toThrow("上传未返回有效图片地址");
    expect(add).not.toHaveBeenCalled();
  });
});
