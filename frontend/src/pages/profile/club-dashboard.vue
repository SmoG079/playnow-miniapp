<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  clubs = ref<any[]>([]),
  index = ref(0),
  club = ref<any>(null),
  stats = ref<any>(null),
  loading = ref(false),
  initialized = ref(false);
async function load() {
  const id = clubs.value[index.value]?.id;
  if (!id) return;
  loading.value = true;
  try {
    [club.value, stats.value] = await Promise.all([
      request(`/clubs/${id}`),
      request(`/clubs/${id}/stats`),
    ]);
  } catch (error: any) {
    uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
onLoad(async (q) => {
  if (!(await s.requireClubAdmin("/pages/profile/club-dashboard"))) return;
  const ids = s.user?.managed_club_ids || [];
  clubs.value = await Promise.all(ids.map((id) => request(`/clubs/${id}`)));
  const i = clubs.value.findIndex((c) => c.id === Number(q?.club_id));
  index.value = i < 0 ? 0 : i;
  initialized.value = true;
  await load();
});
onShow(() => initialized.value && clubs.value.length && load());
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
const go = (p: string) =>
  uni.navigateTo({ url: `${p}?club_id=${clubs.value[index.value]?.id}` });
function callClub() {
  if (club.value?.contact_phone)
    uni.makePhoneCall({ phoneNumber: club.value.contact_phone });
}
</script>
<template>
  <AppShell back title="俱乐部工作台"
    ><view class="content"
      ><picker
        v-if="clubs.length > 1"
        :range="clubs.map((c) => c.name)"
        :value="index"
        @change="
          index = Number($event.detail.value);
          load();
        "
        ><view class="picker-field">{{ clubs[index]?.name }}</view></picker
      ><view v-if="loading && !club" class="loading-state"
        ><wd-loading /><text class="muted">正在加载俱乐部...</text></view
      ><template v-else-if="club"
        ><view class="profile-header"
          ><Photo
            round
            width="75px"
            height="75px"
            :src="club.cover_image"
            fallback="/static/court.jpg"
          /><view
            ><text class="page-title compact">{{ club.name }}</text
            ><text class="muted">{{ club.address }}</text
            ><text v-if="club.contact_phone" class="link" @click="callClub">{{
              club.contact_phone
            }}</text></view
          ></view
        ><view class="profile-stats"
          ><view
            ><text>{{ stats?.total_venues || club.venues?.length || 0 }}</text
            ><text>场地数</text></view
          ><view
            ><text>{{ stats?.today_orders || stats?.today_bookings || 0 }}</text
            ><text>今日订单</text></view
          ><view
            ><text>¥{{ stats?.today_revenue || 0 }}</text
            ><text>今日收入</text></view
          ></view
        ><view class="section-head row between"
          ><text class="section-title"
            >场地管理（{{ club.venues?.length || 0 }}）</text
          ><text class="link" @click="go('/pages/publish/venue-manage')"
            >+ 添加场地</text
          ></view
        ><view class="menu-list"
          ><wd-cell
            v-for="venue in club.venues || []"
            :key="venue.id"
            :title="venue.name"
            :label="`¥${venue.price_per_hour}/小时 · ${venue.status === 'active' ? '正常' : venue.status}`"
            is-link
            @click="
              uni.navigateTo({
                url: `/pages/publish/venue-manage?club_id=${club.id}&venue_id=${venue.id}`,
              })
            "
          /><text v-if="!club.venues?.length" class="muted empty-hint"
            >暂无场地，点击上方添加</text
          ></view
        ><view class="menu-list section-head"
          ><wd-cell
            title="编辑俱乐部"
            is-link
            @click="go('/pages/publish/club-create')" /><wd-cell
            title="场地管理"
            is-link
            @click="go('/pages/admin/venue-manage')" /><wd-cell
            title="订单管理"
            is-link
            @click="go('/pages/admin/order-manage')" /><wd-cell
            title="经营统计"
            is-link
            @click="go('/pages/admin/dashboard')" /><wd-cell
            title="创建赛事"
            is-link
            @click="
              uni.navigateTo({ url: '/pages/publish/tournament-create' })
            " /></view></template
      ><wd-empty v-else-if="initialized" tip="您还没有管理的俱乐部"
        ><wd-button
          @click="uni.navigateTo({ url: '/pages/publish/club-create' })"
          >创建俱乐部</wd-button
        ></wd-empty
      ></view
    ></AppShell
  >
</template>
