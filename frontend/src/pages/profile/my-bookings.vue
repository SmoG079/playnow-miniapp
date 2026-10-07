<script setup lang="ts">
import { ref } from "vue";
import { onReachBottom, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  tabs = [
    ["", "全部"],
    ["pending", "待支付"],
    ["paid", "已支付"],
    ["completed", "已完成"],
    ["cancelled", "已取消"],
    ["refunding", "退款中"],
    ["refunded", "已退款"],
  ],
  active = ref(""),
  items = ref<any[]>([]),
  page = ref(1),
  more = ref(true),
  loading = ref(false);
const names: any = {
  pending: "待支付",
  paid: "已支付",
  completed: "已完成",
  cancelled: "已取消",
  refunding: "退款中",
  refunded: "已退款",
};
async function load(reset = true) {
  if (!s.requireLogin("/pages/profile/my-bookings")) return;
  loading.value = true;
  try {
    const p = reset ? 1 : page.value;
    const r = await request<PageResult<any>>(
      `/users/me/bookings?page=${p}&page_size=20${active.value ? "&status=" + active.value : ""}`,
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
function cancel(b: any) {
  uni.showModal({
    title: b.status === "paid" ? "取消并退款" : "取消预约",
    content: `确定取消订单 ${b.order_no} 吗？`,
    success: async (r) => {
      if (r.confirm) {
        const x: any = await request(`/bookings/${b.id}/cancel`, {
          method: "POST",
          data: { reason: "用户取消" },
        });
        uni.showToast({
          title: x.refund_amount ? `退款 ¥${x.refund_amount}` : "已取消",
          icon: "success",
        });
        load();
      }
    },
  });
}
async function pay(b: any) {
  await request(`/bookings/${b.id}/pay`, { method: "POST" });
  uni.redirectTo({
    url: `/pages/booking/success?booking_id=${b.id}&order_no=${b.order_no}`,
  });
}
</script>
<template>
  <AppShell back title="我的预约"
    ><scroll-view scroll-x class="chip-scroll"
      ><view class="choices nowrap"
        ><button
          v-for="t in tabs"
          :key="t[0]"
          :class="{ chosen: active === t[0] }"
          @click="
            active = t[0];
            load();
          "
        >
          {{ t[1] }}
        </button></view
      ></scroll-view
    ><view class="content list-content"
      ><view v-for="b in items" :key="b.id" class="record-card"
        ><view class="row between"
          ><text class="strong">{{ b.venue_name || "场地预约" }}</text
          ><text class="tag">{{ names[b.status] || b.status }}</text></view
        ><text class="muted small"
          >{{ b.slot_date }} {{ b.slot_start }}–{{ b.slot_end }}</text
        ><text class="muted small">订单 {{ b.order_no }}</text
        ><view class="row between"
          ><text class="price">¥{{ b.amount }}</text
          ><view class="row gap8"
            ><wd-button
              v-if="b.status === 'pending'"
              size="small"
              @click="pay(b)"
              >支付</wd-button
            ><wd-button
              v-if="['pending', 'paid'].includes(b.status)"
              size="small"
              variant="plain"
              type="danger"
              @click="cancel(b)"
              >取消</wd-button
            ></view
          ></view
        ></view
      ><wd-empty
        v-if="!loading && !items.length"
        tip="还没有预约" /><wd-loadmore
        v-if="items.length"
        :state="loading ? 'loading' : more ? 'default' : 'finished'" /></view
  ></AppShell>
</template>
