import { afterEach, expect, it, vi } from "vitest";
vi.mock("../src/services/api",()=>({request:vi.fn()}));
import {request} from "../src/services/api";
import {activityCode,copyActivityLink,sharedActivityId} from "../src/services/activity-sharing";
afterEach(()=>{vi.unstubAllGlobals();vi.clearAllMocks();});
it("accepts direct detail links and WeChat code scenes, rejects malformed identifiers",()=>{
 expect(sharedActivityId({id:"42"})).toBe("42");expect(sharedActivityId({scene:"42"})).toBe("42");
 expect(sharedActivityId({scene:"%"})).toBe("");expect(sharedActivityId({scene:"42&invite=secret"})).toBe("");
});
it("writes the real WeChat code to a local file before previewing",async()=>{
 vi.mocked(request).mockResolvedValue({image_base64:"encoded-png",mime_type:"image/png"});
 const write=vi.fn(o=>o.success());vi.stubGlobal("wx",{env:{USER_DATA_PATH:"wxfile://usr"}});
 vi.stubGlobal("uni",{getFileSystemManager:()=>({writeFile:write})});
 expect(await activityCode("post",42)).toBe("wxfile://usr/playnow-post-42.png");
 expect(request).toHaveBeenCalledWith("/sharing/post/42/code");
 expect(write).toHaveBeenCalledWith(expect.objectContaining({data:"encoded-png",encoding:"base64"}));
});
it("copies only the generated WeChat URL and surfaces clipboard failure",async()=>{
 vi.mocked(request).mockResolvedValue({url:"https://wxaurl.cn/activity"});
 const copy=vi.fn(o=>o.success());vi.stubGlobal("uni",{setClipboardData:copy});
 await copyActivityLink("tournament",7);expect(copy).toHaveBeenCalledWith(expect.objectContaining({data:"https://wxaurl.cn/activity"}));
 copy.mockImplementation(o=>o.fail());await expect(copyActivityLink("tournament",7)).rejects.toThrow("链接复制失败");
});
