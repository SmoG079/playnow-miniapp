<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { openPage } from "../../utils/navigation";
const count = ref(0);
onShow(async () => {
  try {
    count.value =
      (await request<any>("/users/me/notifications/unread-count")).count || 0;
  } catch {}
});
</script>
<template>
  <AppShell active="chat"
    ><view class="content"
      ><view class="page-heading"><text class="page-title">消息</text></view
      ><wd-cell
        title="系统通知"
        icon="notification"
        is-link
        :value="count ? count + ' 条未读' : ''"
        @click="openPage('/pages/message/list')"
      /><view class="empty-state message-empty"
        ><wd-icon name="message" size="48px" color="#137454" /><text
          class="section-title"
          >聊天正在路上</text
        ><text class="muted">活动通知与审核结果可在系统通知查看</text
        ><wd-button
          variant="plain"
          @click="uni.switchTab({ url: '/pages/home/index' })"
          >去广场找球友</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
