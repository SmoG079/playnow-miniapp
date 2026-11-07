<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShareAppMessage } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import ActivityCard from "../../components/ActivityCard.vue";
import type { ActivityCardData, ActivityKind } from "../../domain/activity-card";
import { request, type PageResult } from "../../services/api";
import { useSession } from "../../stores/session";

type ClubActivity = ActivityCardData & { id: number; kind: ActivityKind };
const session = useSession();
const id = ref(0), club = ref<any>(null), community = ref<any>(null), busy = ref(false), failed = ref(false);
const panel = ref<"activities" | "members" | "intro">("activities");
const filters = [
  { value: "", label: "全部" },
  { value: "upcoming", label: "未开始" },
  { value: "ongoing", label: "进行中" },
  { value: "ended", label: "已结束" },
];
const phase = ref(""), activities = ref<ClubActivity[]>([]), activityCount = ref<number | null>(null);
const page = ref(1), more = ref(false), activityLoading = ref(false), activityError = ref(false);
let activityRequest = 0;
async function loadActivities(append = false) {
  const version = ++activityRequest;
  const nextPage = append ? page.value + 1 : 1;
  if (!append) {
    activities.value = [];
    more.value = false;
  }
  activityLoading.value = true;
  activityError.value = false;
  try {
    const filter = phase.value ? "&phase=" + phase.value : "";
    const result = await request<PageResult<ClubActivity>>("/clubs/" + id.value + "/activities?page=" + nextPage + filter);
    if (version !== activityRequest) return;
    page.value = nextPage;
    activities.value = append ? activities.value.concat(result.items) : result.items;
    const total = result.total ?? activities.value.length;
    more.value = activities.value.length < total;
    if (!phase.value) activityCount.value = total;
  } catch {
    if (version === activityRequest) activityError.value = true;
  } finally {
    if (version === activityRequest) activityLoading.value = false;
  }
}
function selectPhase(value: string) {
  if (phase.value === value) return;
  phase.value = value;
  void loadActivities();
}
async function load() {
  failed.value = false;
  try {
    [club.value, community.value] = await Promise.all([
      request("/clubs/" + id.value), request("/clubs/" + id.value + "/community"),
    ]);
  } catch {
    failed.value = true;
  }
}
onLoad(q => {
  id.value = Number(q?.id);
  void load();
  void loadActivities();
  uni.showShareMenu?.({ menus: ["shareAppMessage"] });
});
onShareAppMessage(() => ({
  title: club.value?.name || "网球俱乐部",
  path: "/pages/common/club-detail?id=" + id.value,
  imageUrl: club.value?.cover_image || undefined,
}));
function openActivity(item: ClubActivity) {
  const pageName = item.kind === "tournament" ? "tournament-detail" : "post-detail";
  uni.navigateTo({ url: "/pages/common/" + pageName + "?id=" + item.id });
}
function navigateToClub() {
  const { latitude, longitude, address, name } = club.value;
  if (latitude != null && longitude != null) {
    uni.openLocation({ latitude: Number(latitude), longitude: Number(longitude), address, name });
  } else if (address) {
    uni.setClipboardData({ data: address });
  }
}
async function change(remove?: string) {
  if (busy.value || !session.requireLogin("/pages/common/club-detail?id=" + id.value)) return;
  busy.value = true;
  try {
    await request("/clubs/" + id.value + "/community" + (remove ? "/" + encodeURIComponent(remove) : ""), {
      method: remove || community.value.joined ? "DELETE" : "POST",
    });
    await load();
  } catch (e: any) {
    uni.showToast({ title: e.message || "操作失败", icon: "none" });
  } finally {
    busy.value = false;
  }
}
function confirmRemove(member: { id: string; name: string }) {
  uni.showModal({
    title: "移除成员", content: "确定将" + member.name + "移出俱乐部？",
    success: result => { if (result.confirm) void change(member.id); },
  });
}
</script>

<template>
  <AppShell back title="俱乐部详情">
    <template v-if="club && community">
      <view v-if="club.cover_image" class="club-cover">
        <Photo :src="club.cover_image" width="100%" height="210px" />
      </view>
      <view class="content club-content">
        <view class="club-card">
          <view class="club-identity">
            <view class="club-logo">
              <Photo v-if="club.logo_image" :src="club.logo_image" width="56px" height="56px" />
              <wd-icon v-else name="company" size="27px" />
            </view>
            <view class="club-name">
              <text class="club-title">{{ club.name }}</text>
              <text class="muted small">{{ club.city ? club.city + ' · ' : '' }}网球俱乐部</text>
            </view>
            <wd-button v-if="!community.owner" size="small" :variant="community.joined ? 'plain' : 'base'"
              :loading="busy" @click="change()">{{ community.joined ? '退出' : '加入俱乐部' }}</wd-button>
          </view>
          <view class="club-stats">
            <button @click="panel = 'members'"><text>{{ community.count }}</text><text>成员</text></button>
            <button @click="panel = 'activities'"><text>{{ activityCount ?? '—' }}</text><text>活动</text></button>
          </view>
          <text v-if="club.description" class="description">{{ club.description }}</text>
          <button v-if="club.address" class="club-address" @click="navigateToClub">
            <wd-icon name="location" size="17px" />
            <text>{{ club.address }}</text>
            <wd-icon name="arrow-right" size="15px" />
          </button>
        </view>

        <view class="club-shortcuts">
          <button @click="panel = 'members'"><wd-icon name="user-group" size="22px" /><text>成员</text></button>
          <button v-if="club.address || (club.latitude != null && club.longitude != null)" @click="navigateToClub">
            <wd-icon name="location" size="22px" />
            <text>{{ club.latitude != null && club.longitude != null ? '位置导航' : '复制地址' }}</text>
          </button>
          <button v-if="club.contact_phone" @click="uni.makePhoneCall({ phoneNumber: club.contact_phone })">
            <wd-icon name="phone" size="22px" /><text>联系组织者</text>
          </button>
          <button open-type="share"><wd-icon name="share-alt" size="22px" /><text>分享俱乐部</text></button>
        </view>

        <view class="club-tabs" aria-label="俱乐部详情">
          <button :class="{ selected: panel === 'activities' }" @click="panel = 'activities'">活动</button>
          <button :class="{ selected: panel === 'members' }" @click="panel = 'members'">成员</button>
          <button :class="{ selected: panel === 'intro' }" @click="panel = 'intro'">简介</button>
        </view>
        <template v-if="panel === 'activities'">
          <view class="club-filters">
            <button v-for="filter in filters" :key="filter.label" :class="{ selected: phase === filter.value }"
              @click="selectPhase(filter.value)">{{ filter.label }}</button>
          </view>
          <ActivityCard v-for="activity in activities" :key="activity.kind + '-' + activity.id"
            :item="activity" :kind="activity.kind" @open="openActivity(activity)" />
          <view v-if="activityLoading" class="loading-state"><wd-loading /><text class="muted small">正在加载活动</text></view>
          <view v-else-if="activityError" class="loading-state">
            <text class="muted">活动加载失败</text>
            <wd-button variant="plain" size="small" @click="loadActivities(activities.length > 0)">重试</wd-button>
          </view>
          <wd-button v-else-if="more" block variant="plain" @click="loadActivities(true)">加载更多</wd-button>
          <text v-else-if="!activities.length" class="club-empty muted">暂无符合条件的活动</text>
        </template>
        <view v-else-if="panel === 'members'" class="club-card">
          <text class="section-title">{{ community.owner ? '成员管理' : '俱乐部成员' }}</text>
          <text class="muted">{{ community.count }} 位球友</text>
          <view v-for="member in community.members" :key="member.id" class="row between member-row">
            <text>{{ member.name }}</text>
            <wd-button size="small" variant="text" :disabled="busy" @click="confirmRemove(member)">移除</wd-button>
          </view>
        </view>
        <view v-else class="club-card">
          <text class="section-title">关于俱乐部</text>
          <text class="description">{{ club.description || '欢迎一起打球' }}</text>
          <text v-if="club.rules" class="description">{{ club.rules }}</text>
          <Photo v-for="(image, index) in (club.images || [])" :key="index" :src="image" width="100%" height="160px" />
        </view>
      </view>
    </template>
    <view v-else class="content loading-state">
      <wd-loading v-if="!failed" />
      <text class="muted">{{ failed ? '俱乐部信息加载失败' : '正在加载俱乐部…' }}</text>
      <wd-button v-if="failed" variant="plain" @click="load">重新加载</wd-button>
    </view>
  </AppShell>
</template>

<style scoped>
.club-cover { overflow: hidden; }
.club-content { padding-top: 16px; }
.club-card {
  margin-bottom: 14px;
  padding: 16px;
  background: var(--playnow-surface);
  border: 1px solid var(--playnow-card-border);
  border-radius: var(--playnow-card-radius);
}
.club-identity { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.club-logo {
  width: 56px; height: 56px; display: grid; place-items: center;
  border-radius: 12px; overflow: hidden; color: var(--playnow-brand); background: var(--playnow-brand-soft);
}
.club-name { flex: 1 1 110px; min-width: 0; }
.club-title { display: block; font-size: 21px; font-weight: 650; line-height: 1.4; overflow-wrap: anywhere; }
.club-stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border-block: 1px solid var(--playnow-card-border); margin-top: 16px; }
.club-stats button {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  width: 100%; min-height: 68px; margin: 0; border-radius: 0; background: transparent;
  color: var(--playnow-muted); font-size: 13px;
}
.club-stats button + button { border-left: 1px solid var(--playnow-card-border); }
.club-stats button text:first-child { color: var(--playnow-text); font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
.description { display: block; margin: 12px 0; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--playnow-muted); }
.club-address { display: flex; gap: 8px; align-items: center; width: 100%; min-height: 44px; text-align: left; color: var(--playnow-brand); background: transparent; }
.club-address text { flex: 1; overflow-wrap: anywhere; }
.club-shortcuts { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
.club-shortcuts button {
  flex: 1 1 65px; display: grid; justify-items: center; gap: 4px; min-height: 56px; padding: 8px 4px;
  border-radius: 10px; color: var(--playnow-brand); background: var(--playnow-brand-soft); font-size: 12px;
}
.club-tabs, .club-filters { display: flex; gap: 8px; margin-bottom: 12px; }
.club-tabs button { flex: 1; margin: 0; background: transparent; border-radius: 0; border-bottom: 2px solid var(--playnow-card-border); min-height: 44px; }
.club-tabs .selected { color: var(--playnow-brand); border-color: var(--playnow-brand); font-weight: 600; }
.club-filters { flex-wrap: wrap; gap: 4px 8px; }
.club-filters button { min-height: 44px; padding: 0 10px; margin: 0; background: transparent; font-size: 13px; border-radius: 8px; }
.club-filters .selected { background: var(--playnow-brand-soft); color: var(--playnow-brand); font-weight: 600; }
.club-empty { display: block; text-align: center; padding: 22px 0; }
.member-row { min-height: 60px; padding: 8px 0; gap: 12px; border-top: 1px solid var(--playnow-card-border); }
.member-row > text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
</style>
