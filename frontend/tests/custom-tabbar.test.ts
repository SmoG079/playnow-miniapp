import {afterEach,expect,it,vi} from "vitest";
import fs from "node:fs";
import vm from "node:vm";
import {syncCustomTabBarSelection,syncCustomTabBarUnread} from "../src/utils/tabbar";
afterEach(()=>vi.unstubAllGlobals());
function setup(){
 let route="pages/home/index",definition:any;
 const app={globalData:{} as any},calls:any[]=[];
 const wx={getStorageSync:()=>"token",getWindowInfo:()=>({screenHeight:844,safeArea:{bottom:810}}),switchTab:(opts:any)=>calls.push(opts),navigateTo:vi.fn()};
 const module={exports:[]};vm.runInNewContext(fs.readFileSync(new URL("../src/custom-tab-bar/tabs.js",import.meta.url),"utf8"),{module});
 vm.runInNewContext(fs.readFileSync(new URL("../src/custom-tab-bar/index.js",import.meta.url),"utf8"),{Component:(x:any)=>definition=x,require:()=>module.exports,wx,getApp:()=>app,getCurrentPages:()=>[{route}]});
 function instance(){const bar={data:{...definition.data},...definition.methods,setData(x:any){Object.assign(this.data,x);}};definition.lifetimes.attached.call(bar);return bar;}
 return{app,calls,instance,setRoute:(r:string)=>route=r,show:(bar:any)=>definition.pageLifetimes.show.call(bar)};
}
it("selects immediately and initializes the destination before the route stack settles",()=>{
 const h=setup(),source=h.instance();source.switchTab({currentTarget:{dataset:{index:1}}});
 expect(source.data.selected).toBe(1);expect(h.calls).toHaveLength(1);
 const destination=h.instance();expect(destination.data.selected).toBe(1);
 h.setRoute("pages/booking/club-list");h.show(destination);expect(destination.data.selected).toBe(1);
});
it("does not mistake a stale green icon for an active page",()=>{
 const h=setup(),bar=h.instance();bar.data.selected=3;
 bar.switchTab({currentTarget:{dataset:{index:3}}});expect(h.calls).toHaveLength(1);
});
it("ignores an older failure and rolls back only the current failed navigation",()=>{
 const h=setup(),bar=h.instance();bar.switchTab({currentTarget:{dataset:{index:1}}});bar.switchTab({currentTarget:{dataset:{index:3}}});
 h.calls[0].fail();expect(bar.data.selected).toBe(3);h.calls[1].fail();expect(bar.data.selected).toBe(0);
});
it("a page synchronizes its own tab bar without waiting for requests",()=>{
 const app={globalData:{}},setData=vi.fn();vi.stubGlobal("getApp",()=>app);
 syncCustomTabBarSelection("clubs",{getTabBar:()=>({setData})});
 expect(setData).toHaveBeenCalledWith({selected:1,unread:""});expect((app.globalData as any).playnowTabPath).toBe("pages/booking/club-list");
});

it('clears cached tab badges while a detail page is visible and restores the latest count on return',()=>{
 const setData=vi.fn(),bar={setData},app={globalData:{playnowUnread:3}};
 vi.stubGlobal('getApp',()=>app);vi.stubGlobal('getCurrentPages',()=>[{$vm:{$scope:{getTabBar:()=>bar}}},{route:'pages/chat/system'}]);
 syncCustomTabBarUnread(0);expect(setData).toHaveBeenCalledWith({unread:''});
 syncCustomTabBarSelection('chat',{getTabBar:()=>bar});
 expect(setData).toHaveBeenLastCalledWith({selected:3,unread:''});
});
