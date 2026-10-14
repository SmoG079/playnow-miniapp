import { describe, expect, it, vi } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

// Execute the page's actual submit flow with platform and payment boundaries
// mocked, so the tests catch navigation/storage regressions in the Vue page.
const source = fs.readFileSync(new URL("../src/pages/booking/confirm.vue", import.meta.url), "utf8")
  .match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1]
  .replace(/^import[\s\S]*?;\s*/gm, "");

async function submit(status: string) {
  let onLoad: any;
  const uni = { showToast: vi.fn(), showModal: vi.fn(), navigateTo: vi.fn(),
    redirectTo: vi.fn(), setStorageSync: vi.fn() };
  const returnToActivityForm = vi.fn();
  const context = {
    ref: (value: any) => ({value}), computed: (fn: any) => ({get value(){return fn();}}),
    onLoad: (fn: any) => {onLoad = fn;},
    useSession: () => ({user:{phone:"test-phone"},requireLogin:()=>true}),
    decodeRouteText: (x: any) => x,
    request: async (path: string) => path === "/bookings" ? {id:2,club_id:1} : {name:"test court",club_id:1},
    payBooking: async()=>({}), confirmBookingPaid: async()=>status,
    returnToActivityForm, uni, reviewPay: null as any,
  };
  vm.createContext(context);
  vm.runInContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText+
    ";globalThis.reviewPay = pay;",context);
  await onLoad({slot_ids:"11,12",venue_id:"1",return_mode:"post",date:"2026-10-15",start:"10:00",end:"11:00"});
  await context.reviewPay();
  return {uni,returnToActivityForm};
}

describe("booking confirmation before linking an activity",()=>{
  it.each(["pending","cancelled","refunding","refunded"])("does not return an unusable booking (%s)",async status=>{
    const {uni,returnToActivityForm} = await submit(status);
    expect(uni.setStorageSync).not.toHaveBeenCalled();
    expect(returnToActivityForm).not.toHaveBeenCalled();
    expect(uni.redirectTo).toHaveBeenCalledWith({url:expect.stringContaining("/pages/booking/success?booking_id=2")});
  });
  it("returns the booking only after the backend confirms paid",async()=>{
    const {uni,returnToActivityForm} = await submit("paid");
    expect(uni.setStorageSync).toHaveBeenCalledWith("booking_return",expect.objectContaining({booking_id:2}));
    expect(returnToActivityForm).toHaveBeenCalledWith("post");
    expect(uni.redirectTo).not.toHaveBeenCalled();
  });
});
