<script setup lang="ts">
import { notificationTime } from "../../domain/notifications";
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import MainHeader from "../../components/MainHeader.vue";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { openPage } from "../../utils/navigation";
const unread = ref(0);
const latest = ref<any>(null);
onShow(async () => {
  try {
    const c = await request<any>("/users/me/notifications/unread-count");
    unread.value = c?.count || 0;
    const r = await request<any>("/users/me/notifications?page=1&page_size=1");
    latest.value = r?.items?.[0] || null;
  } catch {}
});
function openSystem() {
  openPage("/pages/chat/conversation?peer=system");
}
</script>
<template>
  <AppShell active="chat"
    ><MainHeader title="消息" /><view class="content main-content"
      ><view class="conv-item" @click="openSystem"
        ><wd-badge :value="unread" :max="99" :hidden="unread === 0" :top="2" :right="2" border custom-class="system-notification-badge"><view class="conv-avatar system"
          ><wd-icon name="notification" size="24px" color="#ffffff" /></view></wd-badge
        ><view class="conv-body"
          ><view class="row between"
            ><text class="strong">系统通知</text
            ><text class="muted small">{{ notificationTime(latest?.created_at) }}</text
            ></view
          ><text class="muted line-clamp">{{
            latest?.title || "活动与审核结果将在此推送"
          }}</text></view
        ></view
      ><view class="empty-state message-empty"
        ><wd-icon name="message" size="48px" color="#147553" /><text
          class="section-title"
          >聊天正在路上</text
        ><text class="muted">活动通知与审核结果可在系统通知查看</text
        ></view
      ></view
    ></AppShell
  >
</template>
<style scoped>
.conv-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}
.conv-avatar {
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.conv-avatar.system {
  background: linear-gradient(135deg, #1d9e75, #147553);
}
.conv-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
:deep(.system-notification-badge) { flex:none; }
.conv-item { background:#fff;border:1px solid var(--playnow-card-border);border-radius:16px; }
.conv-body .row { gap:8px; }
.conv-body .small { white-space:nowrap;font-size:10px; }
</style>
