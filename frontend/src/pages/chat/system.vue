<script setup lang="ts">
import { notificationTime } from "../../domain/notifications";
import { ref } from "vue";
import { onShow, onReachBottom } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import {useInbox} from "../../stores/inbox";
import { request, type PageResult } from "../../services/api";
const items = ref<any[]>([]);
const page = ref(1);
const more = ref(true);
const loading = ref(false);
async function load(reset = true) {
  loading.value = true;
  try {
    const p = reset ? 1 : page.value;
    const r = await request<PageResult<any>>(
      `/users/me/notifications?page=${p}&page_size=20`,
    );
    items.value = reset ? r.items || [] : [...items.value, ...r.items];
    page.value = p + 1;
    more.value = (r.items?.length || 0) === 20;
  } catch {
  } finally {
    loading.value = false;
  }
}
onShow(() => load());
onReachBottom(() => more.value && load(false));
async function read(m: any) {
  if (m.is_read) return;
  try {
    await request(`/users/me/notifications/${m.id}/read`, { method: "PUT" });
    m.is_read = true;
    void useInbox().refresh();
  } catch (error: any) {
    uni.showToast({ title: error.message || "标记已读失败", icon: "none" });
  }
}
</script>
<template>
  <AppShell back title="系统通知"
    ><view class="chat-stream"
      ><view
        v-for="m in items"
        :key="m.id"
        class="bubble-row"
        @click="read(m)"
        ><view class="bubble" :class="{ unread: !m.is_read }"
          ><view class="notification-heading"><wd-badge is-dot :hidden="m.is_read" custom-class="notification-dot" :top="4" :right="4"><view class="notification-status-anchor" /></wd-badge><text class="bubble-title">{{ m.title }}</text></view
          ><text class="bubble-text">{{ m.content }}</text
          ><text class="bubble-time">{{ notificationTime(m.created_at,true) }}</text></view
        ></view
      ><wd-empty v-if="!loading && !items.length" tip="暂无系统通知" /></view
    ></AppShell
  >
</template>
<style scoped>
.chat-stream {
  padding: 12px;
  background: #f5f7f6;
  min-height: 100%;
}
.bubble-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}
.bubble {
  width:100%;
  min-width:0;
  padding: 11px 13px;
  border-radius: var(--playnow-card-radius);
  border: 1px solid var(--playnow-card-border);
  border-left:3px solid transparent;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(20, 117, 83, 0.06);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bubble.unread {
  background: #eaf3ee;
  border-left: 3px solid #147553;
}
.bubble-title {
  font-size: 15px;
  font-weight: 500;
  color: #1f2a26;
}
.bubble-text {
  font-size: 13px;
  color: #5f5e5a;
  line-height: 1.5;
}
.bubble-time {
  font-size: 11px;
  color: #a9a9a3;
  align-self: flex-end;
}
.notification-heading { display:flex;align-items:flex-start;gap:8px;min-width:0; }
.notification-status-anchor { width:8px;height:8px; }
:deep(.notification-dot) { flex:none;margin-top:7px; }
.bubble-title { flex:1;min-width:0;overflow-wrap:anywhere;line-height:1.5; }
.bubble-text { white-space:pre-wrap;overflow-wrap:anywhere; }
</style>
