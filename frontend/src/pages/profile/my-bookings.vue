<script setup lang="ts">
import { ref } from "vue";
import { onReachBottom, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { payBooking, confirmBookingPaid, syncBookingPayment, syncBookingRefund } from "../../services/payment";
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
  refreshing = ref<any>(""),
  loading = ref(false);
const names: any = {
  pending: "待支付",
  paid: "已支付",
  completed: "已完成",
  cancelled: "已取消",
  refunding: "退款中",
  refunded: "已退款",
};
let loadVersion = 0;
async function load(reset = true) {
  if (!reset && (loading.value || !more.value)) return;
  if (!s.requireLogin("/pages/profile/my-bookings")) return;
  const version = ++loadVersion;
  loading.value = true;
  try {
    const p = reset ? 1 : page.value;
    const r = await request<PageResult<any>>(
      `/users/me/bookings?page=${p}&page_size=20${active.value ? "&status=" + active.value : ""}`,
    );
    if (version !== loadVersion) return;
    items.value = reset ? r.items : [...items.value, ...r.items];
    page.value = p + 1;
    more.value = r.items.length === 20;
  } catch (error: any) {
    if (version === loadVersion) uni.showToast({ title: error.message || "预约加载失败", icon: "none" });
  } finally {
    if (version === loadVersion) loading.value = false;
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
  try {
    await payBooking(b.id);
  } catch (e: any) {
    uni.showToast({
      title: e.cancelled ? "已取消支付" : e.message || "支付失败",
      icon: "none",
    });
    return;
  }
  // 收银台返回 ≠ 后端已记账（回调可能延迟或不可达），主动查单确认
  await confirmBookingPaid(b.id);
  uni.redirectTo({
    url: `/pages/booking/success?booking_id=${b.id}&order_no=${b.order_no}`,
  });
}

/** 待支付订单：请后端主动向微信查单，命中成功即刷新为已支付 */
async function refreshStatus(b: any) {
  if (refreshing.value) return;
  refreshing.value = b.id;
  try {
    const res = await syncBookingPayment(b.id);
    if (res?.status && res.status !== "pending") {
      uni.showToast({ title: "已更新为已支付", icon: "success" });
      load();
    } else {
      uni.showToast({ title: "尚未查询到支付结果", icon: "none" });
    }
  } catch (e: any) {
    uni.showToast({ title: e.message || "刷新失败", icon: "none" });
  } finally {
    refreshing.value = "";
  }
}

/** 退款中订单：请后端主动向微信查退款进度，命中终态即刷新 */
async function refreshRefund(b: any) {
  if (refreshing.value) return;
  refreshing.value = b.id;
  try {
    const res = await syncBookingRefund(b.id);
    if (res?.status && res.status !== "refunding") {
      uni.showToast({
        title: res.status === "refunded" ? "退款已到账" : "状态已更新",
        icon: "success",
      });
      load();
    } else {
      uni.showToast({ title: "退款处理中，请稍后查看", icon: "none" });
    }
  } catch (e: any) {
    uni.showToast({ title: e.message || "刷新失败", icon: "none" });
  } finally {
    refreshing.value = "";
  }
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
              v-if="b.status === 'pending'"
              size="small"
              variant="plain"
              :disabled="refreshing === b.id"
              @click="refreshStatus(b)"
              >刷新状态</wd-button
            ><wd-button
              v-if="b.status === 'refunding'"
              size="small"
              variant="plain"
              :disabled="refreshing === b.id"
              @click="refreshRefund(b)"
              >刷新退款</wd-button
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
