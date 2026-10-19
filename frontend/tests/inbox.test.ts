import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {setActivePinia,createPinia} from 'pinia';
const state=vi.hoisted(()=>({loggedIn:true,user:{id:'user-1'} as {id:string}|null}));
vi.mock('../src/stores/session',()=>({useSession:()=>state}));
vi.mock('../src/services/api',()=>({request:vi.fn()}));
import {request} from '../src/services/api';
import {useInbox} from '../src/stores/inbox';
beforeEach(()=>{setActivePinia(createPinia());state.loggedIn=true;state.user={id:'user-1'};vi.mocked(request).mockReset();vi.stubGlobal('uni',{setTabBarBadge:vi.fn(),removeTabBarBadge:vi.fn()});});
afterEach(()=>vi.unstubAllGlobals());
it('combines system and private unread counts without redirecting background failures',async()=>{
 vi.mocked(request).mockResolvedValueOnce({count:2}).mockResolvedValueOnce({count:3,by_conversation:{a:2,b:1}});
 const inbox=useInbox();await inbox.refresh();expect(inbox.total).toBe(5);
 expect(uni.setTabBarBadge).toHaveBeenCalledWith(expect.objectContaining({index:3,text:'5'}));
 expect(request).toHaveBeenCalledWith('/messages/unread-count',{preservePage:true});
 vi.mocked(request).mockRejectedValue(new Error('Not Found'));await inbox.refresh();expect(inbox.total).toBe(5);
});
it('does not apply counts from a previous account',async()=>{
 let resolve:(v:any)=>void=()=>{};
 vi.mocked(request).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValueOnce({count:1,by_conversation:{a:1}});
 const inbox=useInbox();const pending=inbox.refresh();state.user={id:'user-2'};inbox.reset();resolve({count:8});await pending;
 expect(inbox.total).toBe(0);
});
it('clears badge and performs no query after logout',async()=>{
 const inbox=useInbox();state.loggedIn=false;state.user=null;await inbox.refresh();
 expect(request).not.toHaveBeenCalled();expect(uni.removeTabBarBadge).toHaveBeenCalled();
});
function deferred<T>(){let resolve!:(v:T)=>void,reject!:(e:Error)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
async function settle(){for(let i=0;i<12;i++)await Promise.resolve();}
function serverMock(system:number,counts:Record<string,number>){
 const server={system,counts};
 vi.mocked(request).mockImplementation(async(url)=>url.includes('/messages/unread-count')?{count:Object.values(server.counts).reduce((a,b)=>a+b,0),by_conversation:{...server.counts}}:{count:server.system});
 return server;
}
it('removes a system badge immediately before the read request finishes and ignores an older poll',async()=>{
 const server=serverMock(1,{}),inbox=useInbox();await inbox.refresh();
 const oldSystem=deferred<any>(),oldDirect=deferred<any>(),read=deferred<any>();
 vi.mocked(request).mockReturnValueOnce(oldSystem.promise).mockReturnValueOnce(oldDirect.promise).mockReturnValueOnce(read.promise);
 const old=inbox.refresh(),saving=inbox.readSystem(1);
 expect(inbox.systemUnread).toBe(0);expect(inbox.total).toBe(0);expect(uni.removeTabBarBadge).toHaveBeenCalled();
 oldSystem.resolve({count:1});oldDirect.resolve({count:0,by_conversation:{}});await old;expect(inbox.total).toBe(0);
 server.system=0;read.resolve({msg:'ok'});await saving;await settle();expect(inbox.total).toBe(0);
});
it('clears only the opened conversation and retains another unread conversation',async()=>{
 const server=serverMock(0,{a:3,b:2}),inbox=useInbox();await inbox.refresh();
 const read=deferred<any>();vi.mocked(request).mockReturnValueOnce(read.promise);
 const saving=inbox.readConversation('a',100);
 expect(inbox.unreadFor('a')).toBe(0);expect(inbox.unreadFor('b')).toBe(2);expect(inbox.total).toBe(2);
 // A later message arrived after the acknowledged cursor; it remains unread.
 server.counts.a=1;read.resolve({unread_count:1});await saving;await settle();expect(inbox.total).toBe(3);expect(inbox.unreadFor('a')).toBe(1);
});
it('restores unread state when saving a read marker fails',async()=>{
 serverMock(1,{a:2});const inbox=useInbox();await inbox.refresh();
 const failure=deferred<any>();vi.mocked(request).mockReturnValueOnce(failure.promise);
 const saving=inbox.readSystem(2);expect(inbox.total).toBe(2);
 failure.reject(new Error('offline'));await expect(saving).rejects.toThrow('offline');await settle();expect(inbox.total).toBe(3);
});
it('does not restore previous-account unread counts when an old read fails',async()=>{
 serverMock(1,{});const inbox=useInbox();await inbox.refresh();
 const failure=deferred<any>();vi.mocked(request).mockReturnValueOnce(failure.promise);
 const saving=inbox.readSystem(3);state.user={id:'other-user'};inbox.reset();
 failure.reject(new Error('offline'));await expect(saving).rejects.toThrow('offline');await settle();expect(inbox.total).toBe(0);
});
it('keeps concurrent system reads optimistic until every acknowledgement completes',async()=>{
 const server=serverMock(2,{}),inbox=useInbox();await inbox.refresh();
 const first=deferred<any>(),second=deferred<any>();vi.mocked(request).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
 const a=inbox.readSystem(1),b=inbox.readSystem(2);expect(inbox.total).toBe(0);
 server.system=1;first.resolve({msg:'ok'});await a;expect(inbox.total).toBe(0);
 server.system=0;second.resolve({msg:'ok'});await b;await settle();expect(inbox.total).toBe(0);
});
