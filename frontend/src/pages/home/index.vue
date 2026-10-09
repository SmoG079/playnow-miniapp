<script setup lang="ts">
import { computed, ref } from "vue";
import { onPullDownRefresh, onReachBottom, onShow } from "@dcloudio/uni-app";
import MainHeader from "../../components/MainHeader.vue";
import ActivityCard from "../../components/ActivityCard.vue";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { openPage } from "../../utils/navigation";
import { useDiscovery } from "../../stores/discovery";
import { useSession } from "../../stores/session";
import { sortOptions, sortValues, levelOptions, discoveryQuery, ownLevel } from "../../services/discovery";
const location = useDiscovery(), session = useSession();
const tab = ref(0), mode = ref(0), date = ref(""), ntrp = ref(0), sort = ref(0);
const posts = ref<any[]>([]), tournaments = ref<any[]>([]), loading = ref(false);
const types = ["全部约球", "自由约球", "定场约球"];
let loadVersion = 0;
const pages = [1, 1], hasMore = [false, false];
const visiblePosts = computed(() => posts.value.filter(p => p.status !== "closed"));
function listingPath(kind: number, page: number) {
  const extra = discoveryQuery(location.city, sortValues[sort.value], date.value, location.latitude, location.longitude);
  return kind === 0
    ? `/posts?page=${page}&page_size=20&${extra}&activity_type=${["all","free","venue"][mode.value]}${ntrp.value ? "&ntrp_levels=" + levelOptions[ntrp.value] : ""}`
    : `/tournaments?status=open&page=${page}&page_size=20&${extra}`;
}
function canLoadMore(result: PageResult<any>, count: number) {
  return typeof result.total === "number" ? count < result.total : result.items.length === 20;
}
async function load() {
  const version = ++loadVersion;
  posts.value = []; tournaments.value = [];
  pages.fill(1); hasMore.fill(false);
  if (!location.city) { loading.value = false; return; }
  loading.value = true;
  try {
    const [p, t] = await Promise.all([
      request<PageResult<any>>(listingPath(0, 1)),
      request<PageResult<any>>(listingPath(1, 1)),
    ]);
    if (version !== loadVersion) return;
    posts.value = p.items || []; tournaments.value = t.items || [];
    hasMore[0] = canLoadMore(p, posts.value.length);
    hasMore[1] = canLoadMore(t, tournaments.value.length);
  } catch (e: any) {
    if (version === loadVersion) uni.showToast({ title: e.message || "加载失败", icon: "none" });
  } finally { if (version === loadVersion) loading.value = false; }
}
async function loadMore() {
  const kind = tab.value;
  if (loading.value || !hasMore[kind] || !location.city) return;
  const version = loadVersion, page = pages[kind] + 1;
  loading.value = true;
  try {
    const result = await request<PageResult<any>>(listingPath(kind, page));
    if (version !== loadVersion) return;
    const target = kind === 0 ? posts : tournaments;
    target.value = [...target.value, ...(result.items || [])];
    pages[kind] = page;
    hasMore[kind] = canLoadMore(result, page * 20);
  } catch (error: any) {
    if (version === loadVersion) uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally { if (version === loadVersion) loading.value = false; }
}
async function locateCity() {
  try { await location.locate(); }
  catch { uni.showToast({ title: "定位未成功，请手动选择城市", icon: "none" }); }
  await load();
}
async function sortChange(e: any) {
  const selected = Number(e.detail.value);
  if (sortValues[selected] === "distance") {
    try { await location.coordinates(); }
    catch { uni.showToast({ title: "距离排序需要开启定位", icon: "none" }); return; }
  }
  sort.value = selected; await load();
}
function typeChange(e: any) { mode.value = Number(e.detail.value); void load(); }
function levelChange(e: any) { ntrp.value = Number(e.detail.value); void load(); }
function dateChange(e: any) { date.value = e.detail.value; void load(); }
async function myLevel() {
  if (!session.requireLogin("/pages/home/index")) return;
  try { await session.fetchUser(); }
  catch { uni.showToast({ title: "暂时无法读取我的级别，请稍后重试", icon: "none" }); return; }
  const level = ownLevel(session.user?.ntrp_level);
  if (!level) {
    uni.showModal({ title: "完善我的级别", content: "先在个人资料中设置 NTRP 级别，再使用一键筛选。", confirmText: "去设置", success: r => r.confirm && openPage("/pages/profile/edit") });
    return;
  }
  ntrp.value = levelOptions.indexOf(level); await load();
}
onShow(async () => {
  if (!location.city && !location.attempted) { await locateCity(); return; }
  await load();
});
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
onReachBottom(loadMore);
</script>
<template>
  <AppShell active="home"
    ><MainHeader title="首页" @city-change="load" /><view class="content"
      ><view class="text-tabs section-head"
        ><button :class="{ selected: tab === 0 }" @click="tab = 0">
          约球广场</button
        ><button :class="{ selected: tab === 1 }" @click="tab = 1">
          比赛
        </button></view
      ><view class="discovery-filters">
        <view class="filter-line">
          <picker :range="sortOptions" :value="sort" @change="sortChange"><view class="filter-pill"><text>筛选 · {{ sortOptions[sort].replace("按", "") }}</text><wd-icon name="arrow-down" size="12px" /></view></picker>
          <picker v-if="tab === 0" :range="types" :value="mode" @change="typeChange"><view class="filter-pill"><text>{{ types[mode] }}</text><wd-icon name="arrow-down" size="12px" /></view></picker>
        </view>
        <view class="filter-line">
          <picker mode="date" :value="date" @change="dateChange"><view class="filter-pill"><text>{{ date || "日期" }}</text><wd-icon name="arrow-down" size="12px" /></view></picker>
          <picker v-if="tab === 0" :range="levelOptions" :value="ntrp" @change="levelChange"><view class="filter-pill"><text>{{ ntrp ? "NTRP " + levelOptions[ntrp] : "NTRP 等级" }}</text><wd-icon name="arrow-down" size="12px" /></view></picker>
          <button v-if="tab === 0" class="my-level" @click="myLevel">适合我的级别</button>
          <button v-if="date" class="clear-date" @click="date = ''; load()">清除日期</button>
        </view>
      </view>
      <template v-if="tab === 0">
        <ActivityCard v-for="p in visiblePosts" :key="p.id" :item="p" kind="post" @open="openPage('/pages/common/post-detail?id=' + p.id)" />
        <wd-empty v-if="!loading && !visiblePosts.length" tip="暂无约球帖" />
      </template>
      <template v-else>
        <ActivityCard v-for="t in tournaments" :key="t.id" :item="t" kind="tournament" @open="openPage('/pages/common/tournament-detail?id=' + t.id)" />
        <wd-empty v-if="!loading && !tournaments.length" tip="暂无比赛" />
      </template>
      <wd-loading v-if="loading" /></view
    ></AppShell>
</template>

<style scoped>
.discovery-filters{margin-bottom:20px}.filter-line{display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap}
.my-level,.clear-date{margin:0;padding:9px 12px;line-height:20px;font-size:12px;border-radius:12px;background:#e5f0e8;color:#285f40}.my-level::after,.clear-date::after{border:0}
</style>
