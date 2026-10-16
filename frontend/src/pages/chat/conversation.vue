<script setup lang="ts">
import {ref,nextTick,computed,watch} from 'vue';
import {onLoad,onReady,onShow,onHide,onUnload} from '@dcloudio/uni-app';
import AppShell from '../../components/AppShell.vue';
import Photo from '../../components/Photo.vue';
import {useInbox} from '../../stores/inbox';
import {useSession} from '../../stores/session';
import {openPage} from '../../utils/navigation';
import {notificationTime} from '../../domain/notifications';
import {getConversation,getMessages,sendMessage,markMessagesRead,mergeMessages,newMessageKey,type Conversation,type DirectMessage} from '../../services/messages';
const session=useSession();
const id=ref(''),conversation=ref<Conversation|null>(null),messages=ref<DirectMessage[]>([]),input=ref(''),error=ref(''),sending=ref(false),older=ref(false),loadingOlder=ref(false),scrollTo=ref('');
const headerHeight=ref(106),keyboardHeight=ref(0);
const chatHeight=computed(()=>`calc(100vh - ${headerHeight.value}px - ${keyboardHeight.value}px)`);
const keyboardChange=(e:{height:number})=>{keyboardHeight.value=e.height;void bottom();};
onReady(()=>{uni.createSelectorQuery().select('.direct-chat').boundingClientRect((rect:any)=>{if(rect?.top>=0)headerHeight.value=rect.top;}).exec();});
onLoad(()=>uni.onKeyboardHeightChange(keyboardChange));
onUnload(()=>uni.offKeyboardHeightChange(keyboardChange));
let visible=false,version=0,polling=false,timer:ReturnType<typeof setTimeout>|undefined;
let fetchedThrough:number|undefined,acknowledgedThrough=0;
let pending:{content:string;key:string}|null=null;
onLoad(q=>{if(q?.peer==='system'){uni.redirectTo({url:'/pages/chat/system'});return;}id.value=String(q?.id||'');});
function stop(){visible=false;version++;clearTimeout(timer);}
onHide(stop);onUnload(stop);
watch(()=>session.user?.id,()=>{
 const wasVisible=visible;stop();conversation.value=null;messages.value=[];input.value='';pending=null;fetchedThrough=undefined;acknowledgedThrough=0;
 if(wasVisible){visible=true;void refresh(true);}
});
async function bottom(){scrollTo.value='';await nextTick();scrollTo.value='message-'+messages.value[messages.value.length-1]?.id;}
async function acknowledge(){
 const through=fetchedThrough,turn=version;
 if(through&&through>acknowledgedThrough&&visible){await nextTick();await markMessagesRead(id.value,through);if(turn!==version||!visible)return;acknowledgedThrough=Math.max(acknowledgedThrough,through);void useInbox().refresh();}
}
async function refresh(initial=false){
  if(!visible||!id.value||!session.user?.id||polling)return;
  const turn=version;polling=true;
  try{
    if(initial){const data=await getConversation(id.value);if(turn!==version||!visible)return;conversation.value=data;}
    let after=fetchedThrough;
    let batch;
    do{
      batch=await getMessages(id.value,after==null?undefined:{after});
      if(!visible||turn!==version)return;
      messages.value=mergeMessages(messages.value,batch.items);
      if(pending&&batch.items.some(m=>m.is_mine&&m.client_id===pending?.key)){if(input.value.trim()===pending.content)input.value="";pending=null;}
      if(after==null){older.value=batch.has_more;fetchedThrough=batch.items[batch.items.length-1]?.id||0;break;}
      if(batch.items.length){after=batch.items[batch.items.length-1].id;fetchedThrough=after;}
    }while(batch.has_more&&batch.items.length);
    error.value='';await acknowledge();
    if(initial||batch.items.length)await bottom();
  }catch{if(visible&&turn===version)error.value='消息暂时无法加载，可稍后重试';}
  finally{polling=false;if(visible){clearTimeout(timer);timer=setTimeout(()=>void refresh(!conversation.value),5000);}}
}
onShow(()=>{visible=true;if(!session.requireLogin('/pages/chat/conversation?id='+id.value))return;void refresh(!conversation.value);});
async function loadOlder(){
  if(!older.value||loadingOlder.value||!messages.value.length)return;
  const turn=version;loadingOlder.value=true;
  try{const batch=await getMessages(id.value,{before:messages.value[0].id});if(turn!==version||!visible)return;messages.value=mergeMessages(messages.value,batch.items);older.value=batch.has_more;}
  catch{error.value='历史消息加载失败，请重试';}finally{loadingOlder.value=false;}
}
async function send(){
  const content=input.value.trim();if(!content||sending.value||!conversation.value)return;
  if(!pending||pending.content!==content)pending={content,key:newMessageKey()};
  sending.value=true;const turn=version;
  try{
    const message=await sendMessage(id.value,content,pending.key);
    if(turn!==version||!visible)return;
    messages.value=mergeMessages(messages.value,[message]);input.value='';pending=null;error.value='';await acknowledge();await bottom();
  }catch(e:any){if(turn===version)error.value=e.message||'发送失败，内容已保留，请重试';}
  finally{sending.value=false;}
}
</script>
<template>
  <AppShell back flush :title="conversation?.peer.nickname || '私信'">
    <view class="direct-chat" :style="{height:chatHeight,paddingBottom:keyboardHeight?'0':'env(safe-area-inset-bottom)'}">
      <view v-if="conversation" class="post-context" @click="openPage('/pages/common/'+(conversation.activity.kind === 'post' ? 'post' : 'tournament')+'-detail?id='+conversation.activity.id)"><wd-icon name="user-group" size="17px" /><text>关于：{{ conversation.activity.title }}</text><wd-icon name="arrow-right" size="12px" /></view>
      <scroll-view scroll-y class="message-history" :scroll-into-view="scrollTo" @scrolltoupper="loadOlder">
        <view v-if="older" class="older-action" @click="loadOlder">{{ loadingOlder?'加载中…':'查看更早消息' }}</view>
        <view v-if="conversation&&!messages.length" class="start-hint">给发起人发条消息，聊聊这场球局</view>
        <view v-for="m in messages" :id="'message-'+m.id" :key="m.id" class="direct-row" :class="{mine:m.is_mine}">
          <Photo v-if="!m.is_mine" :src="conversation?.peer.avatar_url" width="32px" height="32px" round />
          <view class="direct-message"><text class="message-content">{{ m.content }}</text><text class="message-time">{{ notificationTime(m.created_at) }}</text></view>
        </view>
      </scroll-view>
      <view v-if="error" class="chat-error"><text>{{ error }}</text><text v-if="!sending" @click="refresh(!conversation)">刷新</text></view>
      <view class="message-composer"><wd-textarea v-model="input" :maxlength="2000" :disabled="sending" compact auto-height :adjust-position="false" :show-confirm-bar="false" confirm-type="send" placeholder="发消息给球友…" @confirm="send" /><wd-button size="small" :loading="sending" :disabled="!input.trim()||!conversation" @click="send">发送</wd-button></view>
    </view>
  </AppShell>
</template>
<style scoped>
.direct-chat{height:calc(100vh - 106px);display:flex;flex-direction:column;box-sizing:border-box;padding-bottom:env(safe-area-inset-bottom);background:#f5f7f6}.post-context{display:flex;align-items:center;gap:8px;padding:12px 16px;background:#edf5ed;border-bottom:1px solid #dce7de;font-size:12px;color:#42724b}.post-context text{flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.message-history{flex:1;min-height:0;height:0}.older-action,.start-hint{text-align:center;color:#8b9b90;font-size:12px;padding:16px}.direct-row{display:flex;align-items:flex-start;gap:8px;padding:8px 14px}.direct-row.mine{justify-content:flex-end}.direct-message{max-width:78%;border:1px solid #e0e7e2;border-radius:2px 13px 13px;background:#fff;padding:10px 12px}.mine .direct-message{background:#e2f1df;border-color:#d2e6ce;border-radius:13px 2px 13px 13px}.message-content{display:block;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.6;color:#294134}.message-time{display:block;text-align:right;margin-top:6px;font-size:10px;color:#8a9a8d}.message-composer{display:flex;align-items:flex-end;gap:10px;padding:12px;background:#fff;border-top:1px solid #e0e7e2}.message-composer :deep(.wd-textarea){flex:1;min-width:0;max-height:120px;overflow:auto;border-radius:9px;background:#f5f7f6;padding:8px}.chat-error{display:flex;justify-content:center;gap:12px;padding:8px 12px;color:#8a7560;font-size:12px}.chat-error text:last-child{color:#147553}
</style>
