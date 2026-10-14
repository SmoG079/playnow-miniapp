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
 vi.mocked(request).mockResolvedValueOnce({count:2}).mockResolvedValueOnce({count:3});
 const inbox=useInbox();await inbox.refresh();expect(inbox.total).toBe(5);
 expect(uni.setTabBarBadge).toHaveBeenCalledWith(expect.objectContaining({index:3,text:'5'}));
 expect(request).toHaveBeenCalledWith('/messages/unread-count',{preservePage:true});
 vi.mocked(request).mockRejectedValue(new Error('Not Found'));await inbox.refresh();expect(inbox.total).toBe(5);
});
it('does not apply counts from a previous account',async()=>{
 let resolve:(v:any)=>void=()=>{};
 vi.mocked(request).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValueOnce({count:1});
 const inbox=useInbox();const pending=inbox.refresh();state.user={id:'user-2'};inbox.reset();resolve({count:8});await pending;
 expect(inbox.total).toBe(0);
});
it('clears badge and performs no query after logout',async()=>{
 const inbox=useInbox();state.loggedIn=false;state.user=null;await inbox.refresh();
 expect(request).not.toHaveBeenCalled();expect(uni.removeTabBarBadge).toHaveBeenCalled();
});
