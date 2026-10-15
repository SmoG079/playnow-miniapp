import { afterEach, beforeEach, expect, it, vi } from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { createPinia, setActivePinia } from "pinia";
import { activityShare, enableActivitySharing, isTimelinePreview } from "../src/utils/share";
import { useSession } from "../src/stores/session";

beforeEach(() => { vi.stubGlobal("uni", {}); });
afterEach(() => vi.unstubAllGlobals());

it("enables both chat and Moments menus", () => {
  (uni as any).showShareMenu = vi.fn(); enableActivitySharing();
  expect(uni.showShareMenu).toHaveBeenCalledWith({menus:["shareAppMessage","shareTimeline"]});
});

it("uses the detail route and safe cover without leaking temporary images", () => {
  expect(activityShare("post",42,"周末约球","wxfile://tmp/cover.jpg")).toMatchObject({title:"周末约球",path:"/pages/common/post-detail?id=42",query:"id=42",imageUrl:"/static/tennis.jpg"});
  expect(activityShare("tournament",9,"周末比赛","https://cos.example/cover.jpg").imageUrl).toBe("https://cos.example/cover.jpg");
});

function pageHooks(page: string) {
  const source=fs.readFileSync(new URL(`../src/pages/common/${page}.vue`,import.meta.url),"utf8").match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1];
  const ast=ts.createSourceFile("page.ts",source,ts.ScriptTarget.Latest,true);
  let chat:any,timeline:any;
  const context:any={activityShare,id:{value:42},post:{value:{title:"周末约球"}},t:{value:{title:"周末比赛"}},mine:{value:{invite_token:"partner&token"}},
    onShareAppMessage:(fn:any)=>chat=fn,onShareTimeline:(fn:any)=>timeline=fn};
  vm.createContext(context);
  for(const statement of ast.statements){
    if(ts.isExpressionStatement(statement)&&ts.isCallExpression(statement.expression)&&["onShareAppMessage","onShareTimeline"].includes(statement.expression.expression.getText(ast)))
      vm.runInContext(ts.transpileModule(statement.getText(ast),{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,context);
  }
  return {chat:(event:any={from:"menu"})=>chat(event),timeline:()=>timeline(),ast,context};
}

it.each(["post-detail","tournament-detail"])("%s shares activity identity to chat and Moments",page=>{
  const {chat,timeline}=pageHooks(page);
  expect(chat().path).toBe(`/pages/common/${page}?id=42`);
  expect(timeline()).toMatchObject({query:"id=42"});
  expect(timeline()).not.toHaveProperty("path");
  expect(timeline().query).not.toContain("invite");
});

it("only the explicit partner invitation button includes an invitation",()=>{
  const {chat}=pageHooks("tournament-detail");
  expect(chat({from:"button",target:{dataset:{}}}).path).not.toContain("invite");
  expect(chat({from:"button",target:{dataset:{shareKind:"partner"}}})).toMatchObject({title:"邀请你成为「周末比赛」的搭档",path:"/pages/common/tournament-detail?id=42&invite=partner%26token"});
});

it.each([["post-detail","action"],["tournament-detail","join"]])("%s blocks guest registration before any request",async(page,fn)=>{
  const {ast,context}=pageHooks(page);
  const guard=vi.fn(()=>false);
  Object.assign(context,{s:{requireLogin:guard},invite:{value:"partner"},request:()=>{throw Error("Guest request");},run:()=>{throw Error("Guest command");}});
  const statement=ast.statements.find(s=>ts.isFunctionDeclaration(s)&&s.name?.text===fn)!;
  vm.runInContext(ts.transpileModule(statement.getText(ast),{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,context);
  await context[fn]();
  expect(guard).toHaveBeenCalledWith(expect.stringContaining(`/pages/common/${page}?id=42`));
});

it("Moments is a guest preview, preserves cached credentials and guides entry instead of logging in",()=>{
  const storage=vi.fn(()=>"cached-token"),modal=vi.fn(),navigate=vi.fn();
  vi.stubGlobal("uni",{getLaunchOptionsSync:()=>({scene:1154}),getStorageSync:storage,showModal:modal,navigateTo:navigate});
  expect(isTimelinePreview()).toBe(true);
  setActivePinia(createPinia()); const session=useSession();
  expect(session.loggedIn).toBe(false); expect(session.requireLogin("/pages/common/post-detail?id=42")).toBe(false);
  expect(storage).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled(); expect(modal).toHaveBeenCalled();
});

it("preview requests are anonymous and never refresh tokens or navigate on 401",async()=>{
  const request=vi.fn((options:any)=>options.success({statusCode:401,data:{detail:"denied"}}));
  const navigate=vi.fn();
  vi.stubGlobal("uni",{getLaunchOptionsSync:()=>({scene:1154}),getStorageSync:()=>"cached-token",request,reLaunch:navigate});
  const api=await import("../src/services/api");
  await expect(api.request("/posts/42")).rejects.toThrow("denied");
  expect(request).toHaveBeenCalledOnce();
  expect(request.mock.calls[0][0].header).not.toHaveProperty("Authorization");
  expect(navigate).not.toHaveBeenCalled();
});

it("publishes total minimum and maximum attendance and rejects inverted bounds", async () => {
  const source=fs.readFileSync(new URL("../src/pages/publish/post-create.vue",import.meta.url),"utf8").match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1];
  const ast=ts.createSourceFile("form.ts",source,ts.ScriptTarget.Latest,true);
  const statement=ast.statements.find(s=>ts.isFunctionDeclaration(s)&&s.name?.text==="submit")!;
  const send=vi.fn().mockResolvedValue({id:22}),toast=vi.fn(),redirect=vi.fn(),defer=vi.fn();
  const context:any={form:{title:"周末约球",preferred_date:"2026-11-01",preferred_start:"19:00",preferred_end:"21:00",min_players:4,max_players:6,price:"0",city:"扬州市",address:"测试场地",latitude:32,longitude:119},
    draftReady:{value:true},loading:{value:false},coverUploading:{value:false},locationSelecting:{value:false},images:{value:[]},clubs:{value:[]},clubIndex:{value:-1},
    request:send,uni:{showToast:toast,redirectTo:redirect},clearActivityDraft:vi.fn(),draftOwner:"fixture",completed:false,setTimeout:defer};
  vm.createContext(context);
  vm.runInContext(ts.transpileModule(statement.getText(ast),{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,context);
  await context.submit();
  expect(send).toHaveBeenCalledWith("/posts",expect.objectContaining({data:expect.objectContaining({min_players:4,max_players:6})}));
  defer.mock.calls[0][0]();
  expect(redirect).toHaveBeenCalledWith({url:"/pages/common/post-detail?id=22"});
  send.mockClear();context.form.min_players=7;
  await context.submit();expect(send).not.toHaveBeenCalled();
  expect(toast).toHaveBeenLastCalledWith({title:"最低人数不能大于最大人数",icon:"none"});
});
