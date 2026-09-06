<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  clubs = ref<any[]>([]),
  index = ref(0),
  stats = ref<any>(null),
  loading = ref(false);
async function load() {
  const id = clubs.value[index.value]?.id;
  if (!id) return;
  loading.value = true;
  try {
    stats.value = await request(`/clubs/${id}/stats`);
  } catch (error: any) {
    uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
onLoad(async (q) => {
  if (!(await s.requireClubAdmin("/pages/admin/dashboard"))) return;
  clubs.value = await Promise.all(
    (s.user?.managed_club_ids || []).map((id) => request(`/clubs/${id}`)),
  );
  const i = clubs.value.findIndex((club) => club.id === Number(q?.club_id));
  index.value = i < 0 ? 0 : i;
  await load();
});
</script>
<template>
  <AppShell back title="经营统计"
    ><view class="content"
      ><picker
        v-if="clubs.length > 1"
        :range="clubs.map((club) => club.name)"
        :value="index"
        @change="
          index = Number($event.detail.value);
          load();
        "
        ><view class="picker-field">{{ clubs[index]?.name }}</view></picker
      ><view v-if="loading && !stats" class="loading-state"
        ><wd-loading /><text class="muted">正在加载经营数据...</text></view
      ><view v-if="stats" class="stats-grid"
        ><view
          ><text>{{ stats.total_venues || 0 }}</text
          ><text>场地数</text></view
        ><view
          ><text>¥{{ stats.today_revenue || 0 }}</text
          ><text>今日营收</text></view
        ><view
          ><text>{{ stats.today_orders || 0 }}</text
          ><text>今日订单</text></view
        ><view
          ><text>¥{{ stats.total_revenue || 0 }}</text
          ><text>累计营收</text></view
        ><view
          ><text>{{ stats.total_orders || 0 }}</text
          ><text>累计订单</text></view
        ><view
          ><text>{{ Number(stats.venue_utilization || 0).toFixed(1) }}%</text
          ><text>场地利用率</text></view
        ></view
      ><view v-if="clubs.length" class="menu-list"
        ><wd-cell
          title="订单管理"
          is-link
          @click="
            uni.navigateTo({
              url: '/pages/admin/order-manage?club_id=' + clubs[index].id,
            })
          " /><wd-cell
          title="场地管理"
          is-link
          @click="
            uni.navigateTo({
              url: '/pages/admin/venue-manage?club_id=' + clubs[index].id,
            })
          " /></view
      ><wd-empty
        v-if="!loading && !clubs.length"
        tip="暂无可管理的俱乐部" /></view
  ></AppShell>
</template>
