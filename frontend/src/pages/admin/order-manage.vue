<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onReachBottom } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { bookingStatus } from "../../utils/status";
import { useSession } from "../../stores/session";
const s = useSession();
const clubId = ref(0),
  active = ref(""),
  tabs = [
    ["", "全部"],
    ["pending", "待支付"],
    ["paid", "已支付"],
    ["completed", "已完成"],
    ["cancelled", "已取消"],
    ["refunding", "退款中"],
    ["refunded", "已退款"],
  ],
  items = ref<any[]>([]),
  page = ref(1),
  more = ref(true),
  loading = ref(false);
async function load(reset = true) {
  if (loading.value) return;
  loading.value = true;
  try {
    const p = reset ? 1 : page.value;
    const r = await request<PageResult<any>>(
      `/bookings/club/${clubId.value}?page=${p}&page_size=20${active.value ? "&status=" + active.value : ""}`,
    );
    items.value = reset ? r.items : [...items.value, ...r.items];
    page.value = p + 1;
    more.value = r.items.length === 20;
  } catch (error: any) {
    uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
onLoad(async (q) => {
  clubId.value = Number(q?.club_id);
  if (
    !(await s.requireClubAdmin(
      `/pages/admin/order-manage?club_id=${clubId.value}`,
    ))
  )
    return;
  if (!clubId.value || !s.canManageClub(clubId.value))
    return uni.showToast({ title: "无权管理该俱乐部", icon: "none" });
  await load();
});
onReachBottom(() => more.value && load(false));
function cancel(o: any) {
  uni.showModal({
    title: "取消订单",
    content: `确定取消 ${o.order_no} 吗？`,
    success: async (r) => {
      if (r.confirm) {
        await request(`/bookings/${o.id}/cancel`, {
          method: "POST",
          data: { reason: "管理员取消" },
        });
        load();
      }
    },
  });
}
</script>
<template>
  <AppShell back title="订单管理"
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
      ><view v-for="o in items" :key="o.id" class="record-card"
        ><view class="row between"
          ><text class="strong">{{ o.order_no }}</text
          ><text class="tag">{{ bookingStatus[o.status] }}</text></view
        ><text class="muted small"
          >{{ o.venue_name }} · {{ o.slot_date }} {{ o.slot_start }}</text
        ><view class="row between"
          ><text class="price">¥{{ o.amount }}</text
          ><wd-button
            v-if="['pending', 'paid'].includes(o.status)"
            size="small"
            variant="plain"
            type="danger"
            @click="cancel(o)"
            >取消</wd-button
          ></view
        ></view
      ><wd-empty v-if="!loading && !items.length" tip="暂无订单" /> ></view
    ></AppShell
  >
</template>
