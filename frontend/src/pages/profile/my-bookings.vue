<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onReachBottom, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { payBooking, confirmBookingPaid, syncBookingPayment, syncBookingRefund } from "../../services/payment";
import { useSession } from "../../stores/session";
import { canCancelBooking } from "../../domain/booking";
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
  focus = ref(""),
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
      `/users/me/bookings?page=${p}&page_size=20${active.value ? "&status=" + active.value : ""}${
        focus.value ? "&order_no=" + encodeURIComponent(focus.value) : ""
      }`,
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
onLoad((q) => {
  // 微信「订单管理」的订单详情页路径形如 pages/profile/my-bookings?orderNo=${商品订单号}，
  // 微信会把占位符替换成商户订单号。带上该参数时只展示这一笔，便于从微信支付凭证直达订单。
  focus.value = String(q?.orderNo || "");
});
onShow(() => load());
onReachBottom(() => more.value && load(false));
function clearFocus() {
  focus.value = "";
  load();
}
function cancel(b: any) {
  if (!canCancelBooking(b)) {
    uni.showModal({ title: "不可取消", content: "预约开始前1小时内及开始后不可取消；其他时段取消，已付款订单全额退款。", showCancel: false });
    return;
  }
  const realPaid = b.status === "paid" && !String(b.wx_transaction_id || "").startsWith("dev_");
  uni.showModal({
    title: realPaid ? "取消并全额退款" : "取消预约",
    content: `确定取消订单 ${b.order_no} 吗？${realPaid ? "将申请全额原路退款，到账时间以支付渠道为准。" : ""}`,
    success: async (r) => {
      if (r.confirm) {
        try {
          const x: any = await request(`/bookings/${b.id}/cancel`, {
            method: "POST",
            data: { reason: "用户取消" },
          });
          uni.showToast({
            title: x.status === "refunding" ? "已申请全额退款" : x.status === "refunded" ? "退款已完成" : "已取消",
            icon: "success",
          });
          load();
        } catch (e: any) {
          uni.showToast({ title: e.message || "取消失败，请刷新后重试", icon: "none" });
        }
      }
    },
  });
}
async function pay(b: any) {
  try {
    await payBooking(b.id);
  } catch (e: any) {
    if (e.cancelled) {
      uni.showToast({ title: "已取消支付", icon: "none" });
      return;
    }
    if (e.detail) {
      // 微信侧拒绝调起支付：完整展示错误（含 errno）便于定位限制原因
      uni.showModal({
        title: "支付未成功",
        content: `${e.detail}${e.errno != null ? `\nerrno=${e.errno}` : ""}`,
        showCancel: false,
      });
    } else {
      uni.showToast({ title: e.message || "支付失败", icon: "none" });
    }
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
      uni.showToast({ title: names[res.status] || "状态已更新", icon: "none" });
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
    if (["failed", "closed", "abnormal"].includes(res?.refund_status || "")) {
      uni.showToast({ title: "退款需管理员核对处理", icon: "none" });
      load();
    } else if (res?.status && res.status !== "refunding") {
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
    ><view v-if="focus" class="content"
      ><view class="row between"
        ><text class="muted small">正在查看订单 {{ focus }}</text
        ><wd-button size="small" variant="plain" @click="clearFocus()"
          >查看全部</wd-button
        ></view
      ></view
    ><scroll-view v-if="!focus" scroll-x class="chip-scroll"
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
      ><text class="notice">开始前1小时内及开始后不可取消，其他时段取消全额退款。</text
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
              :disabled="!canCancelBooking(b)"
              @click="cancel(b)"
              >{{ canCancelBooking(b) ? '取消预约' : '不可取消' }}</wd-button
            ></view
          ></view
        ></view
      ><wd-empty
        v-if="!loading && !items.length"
        :tip="focus ? '未找到该订单，可能不属于当前账号' : '还没有预约'" /><wd-loadmore
        v-if="items.length"
        :state="loading ? 'loading' : more ? 'default' : 'finished'" /></view
  ></AppShell>
</template>
