<script setup lang="ts">
import { ref } from "vue";
import { onShow, onReachBottom } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
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
  if (!m.is_read)
    await request(`/users/me/notifications/${m.id}/read`, {
      method: "PUT",
    }).catch(() => {});
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
          ><text class="bubble-title">{{ m.title }}</text
          ><text class="bubble-text">{{ m.content }}</text
          ><text class="bubble-time">{{ m.created_at }}</text></view
        ><view v-if="!m.is_read" class="unread-dot" /></view
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
  max-width: 82%;
  padding: 11px 13px;
  border-radius: 14px;
  border-top-left-radius: 4px;
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
.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e24b4a;
  margin: 6px 0 0 6px;
  flex: none;
}
</style>
