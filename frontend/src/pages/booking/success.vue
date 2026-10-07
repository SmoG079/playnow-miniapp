<script setup lang="ts">
import { ref, onUnmounted } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const booking = ref<any>(null),
  id = ref(""),
  loading = ref(true);
let timer: any,
  count = 0;
const status: any = {
  pending: "支付处理中",
  paid: "支付成功",
  completed: "订单已完成",
  cancelled: "订单已取消",
  refunding: "退款处理中",
  refunded: "退款成功",
};
async function load() {
  try {
    booking.value = await request(`/bookings/${id.value}`);
    if (booking.value.status === "pending" && count++ < 20)
      timer = setTimeout(load, 3000);
  } finally {
    loading.value = false;
  }
}
onLoad((q) => {
  id.value = String(q?.booking_id || "");
  load();
});
onUnmounted(() => clearTimeout(timer));
</script>
<template>
  <AppShell back title="预约结果"
    ><view class="content"
      ><view v-if="booking" class="result-panel"
        ><view class="success-mark"
          ><wd-icon
            :name="booking.status === 'paid' ? 'check' : 'time'"
            size="30px" /></view
        ><text class="page-title">{{
          status[booking.status] || booking.status
        }}</text
        ><text class="muted">订单号 {{ booking.order_no }}</text
        ><view class="summary-card"
          ><view class="summary-row"
            ><text>场地</text><text>{{ booking.venue_name }}</text></view
          ><view class="summary-row"
            ><text>时间</text
            ><text
              >{{ booking.slot_date }} {{ booking.slot_start }}–{{
                booking.slot_end
              }}</text
            ></view
          ><view class="summary-row"
            ><text>金额</text
            ><text class="price">¥{{ booking.amount }}</text></view
          ></view
        ><wd-button
          block
          @click="uni.redirectTo({ url: '/pages/profile/my-bookings' })"
          >查看我的预约</wd-button
        ><wd-button
          block
          variant="plain"
          @click="uni.switchTab({ url: '/pages/home/index' })"
          >返回首页</wd-button
        ></view
      ><wd-loading v-else-if="loading" /></view
  ></AppShell>
</template>
