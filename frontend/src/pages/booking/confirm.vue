<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { returnToActivityForm } from "../../utils/navigation";
const s = useSession(),
  q = ref<any>({}),
  venue = ref<any>(null),
  booking = ref<any>(null),
  paying = ref(false);
const slots = computed(() =>
  String(q.value.slot_ids || "")
    .split(",")
    .filter(Boolean)
    .map(Number),
);
onLoad(async (x) => {
  q.value = x || {};
  if (
    !s.requireLogin(
      "/pages/booking/confirm?" +
        Object.entries(q.value)
          .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
          .join("&"),
    )
  )
    return;
  try {
    venue.value = await request(`/venues/${q.value.venue_id}`);
  } catch {}
});
async function pay() {
  if (paying.value) return;
  if (slots.value.length < 2 || slots.value.some((id) => !Number.isInteger(id) || id <= 0)) {
    uni.showToast({ title: "请选择至少两个连续时段", icon: "none" });
    return;
  }
  if (!s.user?.phone) {
    uni.showModal({
      title: "需要手机号",
      content: "预订场地需要先提供手机号",
      success: (r) =>
        r.confirm && uni.navigateTo({ url: "/pages/profile/edit" }),
    });
    return;
  }
  paying.value = true;
  try {
    booking.value =
      booking.value ||
      (await request("/bookings", {
        method: "POST",
        data: { slot_ids: slots.value },
      }));
    await request(`/bookings/${booking.value.id}/pay`, { method: "POST" });
    uni.showToast({ title: "支付成功", icon: "success" });
    if (["post", "tournament"].includes(q.value.return_mode)) {
      uni.setStorageSync("booking_return", {
        booking_id: booking.value.id,
        club_id: booking.value.club_id || venue.value?.club_id,
        venue_id: q.value.venue_id,
        city: venue.value?.city, address: venue.value?.address,
        latitude: venue.value?.latitude, longitude: venue.value?.longitude,
        venue_name: q.value.venue_name || venue.value?.name,
        slot_date: q.value.date,
        slot_start: q.value.start,
        slot_end: q.value.end,
      });
      returnToActivityForm(q.value.return_mode);
    } else
      uni.redirectTo({
        url: `/pages/booking/success?booking_id=${booking.value.id}&order_no=${booking.value.order_no}`,
      });
  } catch (e: any) {
    if (e.statusCode === 409) booking.value = null;
    uni.showToast({
      title: e.message || "支付失败",
      icon: "none",
    });
  } finally {
    paying.value = false;
  }
}
</script>
<template>
  <AppShell back title="确认预约"
    ><view class="content"
      ><view class="page-heading"
        ><text class="page-title">确认这一次上场</text></view
      ><view class="summary-card"
        ><view class="summary-row"
          ><text class="muted">场地</text
          ><text>{{ q.venue_name || venue?.name }}</text></view
        ><view class="summary-row"
          ><text class="muted">日期</text><text>{{ q.date }}</text></view
        ><view class="summary-row"
          ><text class="muted">时段</text
          ><text>{{ q.start }}–{{ q.end }}</text></view
        ><view class="summary-row"
          ><text class="muted">合计</text
          ><text class="price"
            >¥{{ Number(q.price || 0).toFixed(2) }}</text
          ></view
        ></view
      ><text class="notice">提交后场地将锁定 10 分钟，请及时完成支付。</text
      ><view class="publish-action"
        ><wd-button block :loading="paying" @click="pay"
          >确认支付 ¥{{ Number(q.price || 0).toFixed(2) }}</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
