<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, listAll } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  clubs = ref<any[]>([]),
  index = ref(0),
  stats = ref<any>(null),
  loading = ref(false);
async function load() {
  const id = clubs.value[index.value]?.id;
  if (!id) return;
  stats.value = null;
  loading.value = true;
  try {
    stats.value = await request(`/clubs/${id}/stats`);
  } catch (error: any) {
    uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
let requestedClubId = 0;
onLoad((q) => { requestedClubId = Number(q?.club_id || 0); });
async function refreshClubs() {
  const selected = clubs.value[index.value]?.id || requestedClubId;
  clubs.value = [];
  stats.value = null;
  try {
    if (!(await s.requireClubAdmin("/pages/admin/dashboard"))) return;
    clubs.value = await listAll("/clubs/managed");
    const i = clubs.value.findIndex((c) => c.id === selected);
    index.value = i < 0 ? 0 : i;
    await load();
  } catch (e: any) {
    uni.showToast({ title: e.message || "俱乐部加载失败，请重试", icon: "none" });
  }
}
onShow(refreshClubs);
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
