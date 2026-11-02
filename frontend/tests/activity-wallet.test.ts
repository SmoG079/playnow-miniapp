import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

function receiptFlow(serverState = "SUCCESS", supported = true, cancelled = false) {
  let source = fs.readFileSync(new URL("../src/pages/profile/activity-wallet.vue", import.meta.url), "utf8").match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1];
  source = source.replace(/^import[\s\S]*?;\s*/gm, "").replace(/\/\/ #ifndef MP-WEIXIN[\s\S]*?\/\/ #endif/g, "");
  const confirmation={mchId:"test-merchant",appId:"test-app",package:"opaque-package"};
  let reads=0;
  const request=vi.fn(async()=>++reads===1?{state:"WAIT_USER_CONFIRM",confirmation}:{state:serverState});
  const native=vi.fn((opts:any)=>cancelled?opts.fail({errMsg:"cancel"}):opts.success({}));
  const context:any={ref:(v:any)=>({value:v}),useSession:()=>({requireLogin:()=>true}),onLoad:vi.fn(),onShow:vi.fn(),request,wx:{canIUse:()=>supported,requestMerchantTransfer:native},uni:{},Map,Math,Date,Promise};
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText+";globalThis.confirmReceiptForTest=confirmReceipt;",context);
  return {run:()=>context.confirmReceiptForTest(7),request,native,confirmation};
}

describe("merchant transfer receipt confirmation",()=>{
  it("uses merchant parameters and confirms success through the server",async()=>{
    const flow=receiptFlow();expect(await flow.run()).toBe(true);
    expect(flow.native).toHaveBeenCalledWith(expect.objectContaining(flow.confirmation));
    expect(flow.request).toHaveBeenCalledTimes(2);
  });
  it("does not treat opening the native sheet as money received",async()=>{
    const flow=receiptFlow("WAIT_USER_CONFIRM");expect(await flow.run()).toBe(false);
  });
  it("keeps interrupted bills resumable without creating another withdrawal",async()=>{
    const flow=receiptFlow("SUCCESS",true,true);await expect(flow.run()).rejects.toThrow("已暂停");
    expect(flow.request).toHaveBeenCalledTimes(1);
    expect(flow.request).toHaveBeenCalledWith("/activity-wallet/transfers/7/sync",{method:"POST"});
  });
  it("requires a supported WeChat client",async()=>{
    const flow=receiptFlow("SUCCESS",false);await expect(flow.run()).rejects.toThrow("请更新微信版本");expect(flow.native).not.toHaveBeenCalled();
  });
});
