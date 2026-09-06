<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const message = ref<any>(null);
onLoad(async (q) => {
  message.value = await request(`/users/me/notifications/${q?.id}`);
  if (!message.value.is_read)
    await request(`/users/me/notifications/${q?.id}/read`, { method: "PUT" });
});
</script>
<template>
  <AppShell back title="通知详情"
    ><view v-if="message" class="content article"
      ><text class="page-title">{{ message.title }}</text
      ><text class="muted small">{{ message.created_at }}</text
      ><text class="body-copy">{{ message.content }}</text></view
    ><wd-loading v-else
  /></AppShell>
</template>
