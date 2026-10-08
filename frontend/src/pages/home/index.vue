<script setup lang="ts">
import { computed, ref } from "vue";
import { onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { openPage } from "../../utils/navigation";
import { useDiscovery } from "../../stores/discovery";
import { useSession } from "../../stores/session";
import { sortOptions, sortValues, levelOptions, discoveryQuery, ownLevel } from "../../services/discovery";
const location = useDiscovery(), session = useSession();
const statusTop = Number(uni.getSystemInfoSync().statusBarHeight || 24) + 12;
const tab = ref(0), mode = ref(0), date = ref(""), ntrp = ref(0), sort = ref(0);
const posts = ref<any[]>([]), tournaments = ref<any[]>([]), loading = ref(false);
const cityPanel = ref(false);
const types = ["全部约球", "自由约球", "定场约球"];
let loadVersion = 0;
const visiblePosts = computed(() => posts.value.filter(p => p.status !== "closed"));
async function load() {
  const version = ++loadVersion;
  posts.value = []; tournaments.value = [];
  if (!location.city) { loading.value = false; return; }
  loading.value = true;
  try {
    const extra = discoveryQuery(location.city, sortValues[sort.value], date.value, location.latitude, location.longitude);
    const [p, t] = await Promise.all([
      request<PageResult<any>>(`/posts?page=1&page_size=20&${extra}&activity_type=${["all","free","venue"][mode.value]}${ntrp.value ? "&ntrp_levels=" + levelOptions[ntrp.value] : ""}`),
      request<PageResult<any>>(`/tournaments?status=open&page=1&page_size=20&${extra}`),
    ]);
    if (version !== loadVersion) return;
    posts.value = p.items || []; tournaments.value = t.items || [];
  } catch (e: any) {
    if (version === loadVersion) uni.showToast({ title: e.message || "加载失败", icon: "none" });
  } finally { if (version === loadVersion) loading.value = false; }
}
async function locateCity() {
  try { await location.locate(); }
  catch { uni.showToast({ title: "定位未成功，请手动选择城市", icon: "none" }); }
  cityPanel.value = false;
  await load();
}
function cityChange(e: any) { location.selectRegion(e.detail.value); cityPanel.value = false; void load(); }
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
</script>
<template>
  <AppShell active="home"
    ><view class="home-header" :style="{ paddingTop: statusTop + 'px' }">
      <text class="brand">PlayNow<text class="brand-dot">.</text></text>
      <view class="headline"><text class="page-title">今天，球场见。</text></view>
    </view
    ><view class="content"
      ><view class="city-header">
        <view class="city-pill" @click="cityPanel = true"><wd-icon name="location" size="10px" /><text>{{ location.city || "城市" }}</text><wd-icon name="arrow-down" size="8px" /></view>
      </view>
<view class="text-tabs section-head"
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
      <template v-if="tab === 0"
        ><view
          v-for="p in visiblePosts"
          :key="p.id"
          class="activity-card"
          @click="openPage('/pages/common/post-detail?id=' + p.id)"
          ><view class="row between"
            ><view class="row gap8"
              ><Photo
                round
                width="40px"
                height="40px"
                :src="p.user_avatar"
                fallback="/static/tennis.jpg"
              /><view
                ><text class="strong">{{ p.user_nickname || "匿名球友" }}</text
                ><text class="muted small">{{ p.created_at }}</text></view
              ></view
            ><text class="tag">{{ p.venue_id ? "订场" : "自由" }}</text></view
          ><text class="activity-title">{{ p.title }}</text
          ><view class="row between"
            ><text class="muted small"
              >{{ p.preferred_date }} {{ p.preferred_start }}–{{
                p.preferred_end
              }}</text
            ><text class="link"
              >{{ p.registration_count || 0 }}/{{ p.players_needed }} 人</text
            ></view
          ></view
        ><wd-empty
          v-if="!loading && !visiblePosts.length"
          tip="暂无约球帖" /><wd-loading v-if="loading" /></template
      ><template v-else
        ><view
          v-for="t in tournaments"
          :key="t.id"
          class="venue-card"
          @click="openPage('/pages/common/tournament-detail?id=' + t.id)"
          ><Photo
            width="100%"
            height="170px"
            :src="t.cover_image"
            fallback="/static/tennis.jpg"
            mode="aspectFill"
          /><view class="venue-card-body"
            ><text class="section-title">{{ t.title }}</text
            ><text class="muted">{{ t.club_name }} · {{ t.start_time }}</text
            ><text class="link"
              >{{ t.current_participants }}/{{ t.max_participants }} 人</text
            ></view
          ></view
        ><wd-empty
          v-if="!loading && !tournaments.length"
          tip="暂无比赛" /></template></view
    ><wd-popup v-model="cityPanel" position="bottom" closable safe-area-inset-bottom custom-style="border-radius:20px 20px 0 0">
      <view class="city-options"><text class="section-title">选择城市</text>
        <wd-button block :loading="location.locating" @click="locateCity">定位到当前城市</wd-button>
        <picker mode="region" :value="location.region" @change="cityChange"><view class="filter-pill"><text>手动选择城市</text><wd-icon name="arrow-right" size="14px" /></view></picker>
      </view>
    </wd-popup></AppShell>
</template>

<style scoped>
.city-options{padding:28px 24px;display:flex;flex-direction:column;gap:20px}.city-options .filter-pill{justify-content:space-between}
.city-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.headline{display:flex;align-items:center;justify-content:space-between}
.city-pill{display:flex;align-items:center;justify-content:center;gap:2px;box-sizing:border-box;width:68px;background:#123b2c;color:white;padding:7px 4px;border-radius:20px;font-size:11px;font-weight:600}.city-pill text{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.discovery-filters{margin-bottom:20px}.filter-line{display:flex;align-items:center;gap:8px;margin-top:10px;flex-wrap:wrap}
.filter-pill{display:flex;align-items:center;gap:8px;padding:10px 12px;border:1px solid #e3e8e5;border-radius:12px;font-size:13px;background:white;color:#283e32}
.my-level,.clear-date{margin:0;padding:9px 12px;line-height:20px;font-size:12px;border-radius:12px;background:#e5f0e8;color:#285f40}.my-level::after,.clear-date::after{border:0}
.city-hint{padding:18px;text-align:center;color:#789084;background:#edf4ef;border-radius:14px;margin-bottom:20px}
</style>
