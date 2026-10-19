import {defineStore} from 'pinia';
import {ref,computed} from 'vue';
import {request} from '../services/api';
import {markMessagesRead} from '../services/messages';
import {useSession} from './session';
import {syncCustomTabBarUnread} from '../utils/tabbar';
export const useInbox=defineStore('inbox',()=>{
 const systemUnread=ref(0),conversations=ref<Record<string,number>>({});
 const directUnread=computed(()=>Object.values(conversations.value).reduce((sum,n)=>sum+n,0));
 const total=computed(()=>systemUnread.value+directUnread.value);
 let active=false,revision=0,epoch=0,again=false,timer:ReturnType<typeof setTimeout>|undefined;
 let flight:Promise<void>|undefined;
 const pending=new Map<string,{promise:Promise<void>}>();
 function badge(){
  syncCustomTabBarUnread(total.value);
  const fail=()=>{};
  if(total.value)uni.setTabBarBadge?.({index:3,text:total.value>99?'99+':String(total.value),fail});
  else uni.removeTabBarBadge?.({index:3,fail});
 }
 function reset(){epoch++;revision++;again=false;pending.clear();systemUnread.value=0;conversations.value={};badge();}
 function valid(owner:string|undefined,stamp:number){const s=useSession();return stamp===epoch&&s.loggedIn&&s.user?.id===owner;}
 async function refresh():Promise<void>{
  const session=useSession(),owner=session.user?.id;
  if(!session.loggedIn||!owner){reset();return;}
  if(pending.size){again=true;return;}
  if(flight){again=true;await flight;return;}
  const turn=revision,stamp=epoch;
  const task=(async()=>{
   try{
    const [s,d]=await Promise.all([request<{count:number}>('/users/me/notifications/unread-count',{preservePage:true}),request<{count:number;by_conversation:Record<string,number>}>('/messages/unread-count',{preservePage:true})]);
    if(turn!==revision||!valid(owner,stamp)||pending.size)return;
    if(!d.by_conversation||typeof d.by_conversation!=='object')throw new Error('Invalid unread response');
    systemUnread.value=s.count||0;conversations.value=d.by_conversation;badge();
   }catch{/* Preserve known unread state on a background network failure. */}
  })();
  flight=task;
  try{await task;}finally{
   if(flight===task)flight=undefined;
   if(again&&!pending.size){again=false;void refresh();}
   else if(active){clearTimeout(timer);timer=setTimeout(()=>void refresh(),15000);}
  }
 }
 function unreadFor(id:string){return conversations.value[id]||0;}
 function mutate(key:string,consume:()=>void,restore:()=>void,save:()=>Promise<any>,apply?:(response:any)=>void):Promise<void>{
  const existing=pending.get(key);if(existing)return existing.promise;
  const owner=useSession().user?.id,stamp=epoch;
  if(!owner||!useSession().loggedIn)return Promise.reject(new Error('请先登录'));
  const entry={promise:Promise.resolve()};pending.set(key,entry);
  revision++;consume();badge();
  entry.promise=(async()=>{
   try{const result=await save();if(valid(owner,stamp)){apply?.(result);badge();}}
   catch(error){if(valid(owner,stamp)){restore();badge();}throw error;}
   finally{
    if(pending.get(key)===entry){pending.delete(key);revision++;if(!pending.size){again=false;void refresh();}}
   }
  })();
  return entry.promise;
 }
 function readSystem(id:number){
  const amount=Math.min(1,systemUnread.value);
  return mutate('system:'+id,()=>{systemUnread.value-=amount;},()=>{systemUnread.value+=amount;},()=>request(`/users/me/notifications/${id}/read`,{method:'PUT',preservePage:true}));
 }
 function readConversation(id:string,through:number){
  const previous=unreadFor(id);
  return mutate('direct:'+id,()=>{conversations.value[id]=0;},()=>{conversations.value[id]=previous;},()=>markMessagesRead(id,through),result=>{conversations.value[id]=result.unread_count||0;});
 }
 function start(){active=true;clearTimeout(timer);void refresh();}
 function stop(){active=false;revision++;again=false;clearTimeout(timer);}
 return {systemUnread,directUnread,total,refresh,reset,start,stop,unreadFor,readSystem,readConversation};
});
