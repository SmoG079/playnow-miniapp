<script setup lang="ts">
import ChoicePicker from "../../components/ChoicePicker.vue";
import { ref } from "vue";
import { onLoad, onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, listAll } from "../../services/api";
import { useSession } from "../../stores/session";
const statusNames: Record<string, string> = { active: "正常", maintenance: "维护中", closed: "已关闭" };
const s = useSession(),
  clubs = ref<any[]>([]),
  index = ref(0),
  club = ref<any>(null),
  stats = ref<any>(null),
  loading = ref(false);
async function load() {
  const id = clubs.value[index.value]?.id;
  if (!id) return;
  club.value = stats.value = null;
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
let requestedClubId = 0;
onLoad((q) => { requestedClubId = Number(q?.club_id || 0); });
async function refreshClubs() {
  const selected = clubs.value[index.value]?.id || requestedClubId;
  clubs.value = [];
  stats.value = null;
  club.value = null;
  try {
    if (!(await s.requireClubAdmin("/pages/profile/club-dashboard"))) return;
    clubs.value = await listAll("/clubs/managed");
    const i = clubs.value.findIndex((c) => c.id === selected);
    index.value = i < 0 ? 0 : i;
    await load();
  } catch (e: any) {
    uni.showToast({ title: e.message || "俱乐部加载失败，请重试", icon: "none" });
  }
}
onShow(refreshClubs);
onPullDownRefresh(() => refreshClubs().finally(() => uni.stopPullDownRefresh()));
const go = (p: string) =>
  uni.navigateTo({ url: `${p}?club_id=${clubs.value[index.value]?.id}` });
function callClub() {
  if (club.value?.contact_phone)
    uni.makePhoneCall({ phoneNumber: club.value.contact_phone });
}
</script>
<template>
  <AppShell back title="俱乐部工作台"
    ><view class="content list-content"
      ><ChoicePicker title="选择俱乐部"
        v-if="clubs.length > 1"
        :range="clubs.map((c) => c.name)"
        :value="index"
        @change="
          index = Number($event.detail.value);
          load();
        "
        ><view class="picker-field">{{ clubs[index]?.name }}</view></ChoicePicker><view v-if="loading && !club" class="loading-state"
        ><wd-loading /><text class="muted">正在加载俱乐部...</text></view
      ><template v-else-if="club"
        ><view class="profile-header"
          ><Photo
            round
            width="75px"
            height="75px"
            :src="club.logo_image || club.cover_image"
            fallback="/static/tennis.jpg"
          /><view
            ><text class="page-title compact">{{ club.name }}</text
            ><text class="muted">{{ club.address }}</text
            ><text v-if="club.contact_phone" class="link" @click="callClub">{{
              club.contact_phone
            }}</text></view
          ></view
        ><view class="menu-list section-head"
          ><wd-cell
            title="编辑俱乐部"
            is-link
            @click="go('/pages/publish/club-create')" /><wd-cell
            title="社群详情与成员"
            is-link
            @click="uni.navigateTo({url:'/pages/common/club-detail?id='+club.id})" /><wd-cell
            title="历史预约订单"
            is-link
            @click="go('/pages/admin/order-manage')" /><wd-cell
            title="本人活动提现"
            is-link
            @click="go('/pages/profile/activity-wallet')" /><wd-cell
            title="创建赛事"
            is-link
            @click="
              uni.navigateTo({ url: '/pages/publish/tournament-create' })
            " /></view></template
      ><wd-empty v-else-if="!loading" tip="您还没有管理的俱乐部"
        ><wd-button
          @click="uni.navigateTo({ url: '/pages/publish/club-create' })"
          >创建俱乐部</wd-button
        ></wd-empty
      ></view
    ></AppShell
  >
</template>
