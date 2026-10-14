<script setup lang="ts">
import {notificationTime} from '../../domain/notifications';
import {ref,watch} from 'vue';
import {onShow,onHide,onUnload,onReachBottom} from '@dcloudio/uni-app';
import MainHeader from '../../components/MainHeader.vue';
import AppShell from '../../components/AppShell.vue';
import Photo from '../../components/Photo.vue';
import {request} from '../../services/api';
import {getConversations,type Conversation} from '../../services/messages';
import {openPage} from '../../utils/navigation';
import {useSession} from '../../stores/session';
const session=useSession(),unread=ref(0),latest=ref<any>(null),conversations=ref<Conversation[]>([]),error=ref('');
let visible=false,version=0,loading=false,page=1,more=false,timer:ReturnType<typeof setTimeout>|undefined;
function stop(){visible=false;version++;clearTimeout(timer);}
onHide(stop);onUnload(stop);
watch(()=>session.user?.id,()=>{version++;conversations.value=[];latest.value=null;unread.value=0;if(visible)void load();});
async function load(append=false){
 if(!visible||!session.loggedIn||loading)return;
 const turn=version;loading=true;
 try{
  const next=append?page+1:1;
  const [count,notification,threads]=await Promise.all([request<any>('/users/me/notifications/unread-count'),request<any>('/users/me/notifications?page=1&page_size=1'),getConversations(next)]);
  if(turn!==version||!visible)return;
  unread.value=count.count||0;latest.value=notification.items?.[0]||null;conversations.value=append?[...conversations.value,...threads.items]:threads.items;page=next;more=conversations.value.length<(threads.total||0);error.value='';
 }catch{if(turn===version)error.value='消息暂时无法加载，请稍后重试';}
 finally{loading=false;if(visible){clearTimeout(timer);timer=setTimeout(()=>void load(),10000);}}
}
onShow(()=>{visible=true;if(!session.loggedIn){conversations.value=[];latest.value=null;unread.value=0;return;}void load();});
onReachBottom(()=>{if(more)void load(true);});
</script>
<template>
 <AppShell active="chat"><MainHeader title="消息" /><view class="content main-content">
  <view v-if="!session.loggedIn" class="empty-state"><text class="muted">登录后即可与球友私信沟通</text><wd-button @click="session.requireLogin('/pages/chat/index')">登录</wd-button></view>
  <template v-else>
   <view class="conv-item" @click="openPage('/pages/chat/system')">
    <wd-badge :value="unread" :max="99" :hidden="unread===0" :top="2" :right="2" border><view class="conv-avatar system"><wd-icon name="notification" size="24px" color="#fff" /></view></wd-badge>
    <view class="conv-body"><view class="row between"><text class="strong">系统通知</text><text class="muted small">{{ notificationTime(latest?.created_at) }}</text></view><text class="muted line-clamp">{{ latest?.title || '活动与审核结果将在此推送' }}</text></view>
   </view>
   <view v-for="c in conversations" :key="c.id" class="conv-item direct-conversation" @click="openPage('/pages/chat/conversation?id='+c.id)">
    <wd-badge :value="c.unread_count" :max="99" :hidden="c.unread_count===0" :top="2" :right="2" border><Photo :src="c.peer.avatar_url" width="46px" height="46px" round /></wd-badge>
    <view class="conv-body"><view class="row between"><text class="strong peer-name">{{ c.peer.nickname }}</text><text class="muted small">{{ notificationTime(c.last_message_at) }}</text></view><text class="muted line-clamp">{{ c.last_message || '开始聊天' }}</text><text class="conversation-post">{{ c.post.title }}</text></view>
   </view>
   <view v-if="error" class="list-error"><text>{{ error }}</text><text @click="load()">重试</text></view>
   <view v-else-if="!conversations.length" class="empty-state message-empty"><wd-icon name="message" size="42px" color="#147553" /><text class="section-title">和球友聊聊下一场球</text><text class="muted">在约球详情点击「发消息」即可联系发起人</text></view>
  </template>
 </view></AppShell>
</template>
<style scoped>
.conv-item{display:flex;align-items:center;gap:12px;padding:16px;background:#fff;border:1px solid var(--playnow-card-border);border-radius:16px;margin-bottom:12px}.conv-avatar{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center}.system{background:linear-gradient(135deg,#1d9e75,#147553)}.conv-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}.conv-body .row{gap:8px}.small{white-space:nowrap;font-size:10px}.peer-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.conversation-post{font-size:10px;color:#9aa89e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.list-error{display:flex;justify-content:center;gap:12px;padding:16px;font-size:12px;color:#829389}.list-error text:last-child{color:#147553}
</style>
