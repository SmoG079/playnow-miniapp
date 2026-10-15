import {defineStore} from 'pinia';
import {ref,computed} from 'vue';
import {request} from '../services/api';
import {useSession} from './session';
import {syncCustomTabBarUnread} from '../utils/tabbar';
export const useInbox=defineStore('inbox',()=>{
 const systemUnread=ref(0),directUnread=ref(0),total=computed(()=>systemUnread.value+directUnread.value);
 let active=false,loading=false,generation=0,timer:ReturnType<typeof setTimeout>|undefined;
 function badge(){
  syncCustomTabBarUnread(total.value);
  const fail=()=>{};
  if(total.value)uni.setTabBarBadge?.({index:3,text:total.value>99?'99+':String(total.value),fail});
  else uni.removeTabBarBadge?.({index:3,fail});
 }
 function reset(){generation++;systemUnread.value=0;directUnread.value=0;badge();}
 async function refresh(){
  const session=useSession(),owner=session.user?.id;
  if(!session.loggedIn||!owner){reset();return;}
  if(loading)return;
  const turn=generation;loading=true;
  try{
   const [s,d]=await Promise.all([request<{count:number}>('/users/me/notifications/unread-count',{preservePage:true}),request<{count:number}>('/messages/unread-count',{preservePage:true})]);
   if(turn!==generation||useSession().user?.id!==owner||!useSession().loggedIn)return;
   systemUnread.value=s.count||0;directUnread.value=d.count||0;badge();
  }catch{/* Background checks leave the current page and previous count intact. */}
  finally{loading=false;if(active){clearTimeout(timer);timer=setTimeout(()=>void refresh(),15000);}}
 }
 function start(){active=true;clearTimeout(timer);void refresh();}
 function stop(){active=false;generation++;clearTimeout(timer);}
 return {systemUnread,directUnread,total,refresh,reset,start,stop};
});
