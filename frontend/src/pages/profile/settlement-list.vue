<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { settlementStatus } from "../../utils/status";
const items = ref<any[]>([]);
onLoad(
  async () =>
    (items.value = (
      await request<PageResult<any>>(
        "/bookings/settlements?page=1&page_size=50",
      )
    ).items),
);
async function retry(x: any) {
  await request(`/bookings/settlements/${x.id}/retry`, { method: "POST" });
  uni.showToast({ title: "已重试", icon: "success" });
}
</script>
<template>
  <AppShell back title="分账记录"
    ><view class="content list-content"
      ><view v-for="x in items" :key="x.id" class="record-card"
        ><view class="row between"
          ><text class="strong">{{ x.order_no }}</text
          ><text class="tag">{{
            settlementStatus[x.status] || x.status
          }}</text></view
        ><text class="muted small"
          >订单 ¥{{ x.total_amount }} · 俱乐部 ¥{{ x.club_amount }}</text
        ><text v-if="x.fail_reason" class="error-text">{{ x.fail_reason }}</text
        ><wd-button v-if="x.status === 'failed'" size="small" @click="retry(x)"
          >重试</wd-button
        ></view
      ><wd-empty v-if="!items.length" tip="暂无分账记录" /></view
  ></AppShell>
</template>
