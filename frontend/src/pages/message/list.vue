<script setup lang="ts">
import { ref } from "vue";
import { onReachBottom, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  items = ref<any[]>([]),
  page = ref(1),
  more = ref(true),
  loading = ref(false);
async function load(reset = true) {
  if (!s.requireLogin("/pages/message/list")) return;
  loading.value = true;
  try {
    const p = reset ? 1 : page.value,
      r = await request<PageResult<any>>(
        `/users/me/notifications?page=${p}&page_size=20`,
      );
    items.value = reset ? r.items : [...items.value, ...r.items];
    page.value = p + 1;
    more.value = r.items.length === 20;
  } finally {
    loading.value = false;
  }
}
onShow(() => load());
onReachBottom(() => more.value && load(false));
async function open(m: any) {
  if (!m.is_read)
    await request(`/users/me/notifications/${m.id}/read`, { method: "PUT" });
  uni.navigateTo({ url: `/pages/message/detail?id=${m.id}` });
}
</script>
<template>
  <AppShell back title="系统通知"
    ><view class="content list-content"
      ><view
        v-for="m in items"
        :key="m.id"
        :class="['message-card', { unread: !m.is_read }]"
        @click="open(m)"
        ><view class="row between"
          ><text class="strong">{{ m.title }}</text
          ><text v-if="!m.is_read" class="unread-dot" /></view
        ><text class="muted line-clamp">{{ m.content }}</text
        ><text class="muted small">{{ m.created_at }}</text></view
      ><wd-empty v-if="!loading && !items.length" tip="暂无通知" /></view
  ></AppShell>
</template>
