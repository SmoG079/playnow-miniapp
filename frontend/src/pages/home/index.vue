<script setup lang="ts">
import ChoicePicker from "../../components/ChoicePicker.vue";
import { computed, ref } from "vue";
import { onPullDownRefresh, onReachBottom, onShow, onHide, onUnload } from "@dcloudio/uni-app";
import { visibleInDiscovery, registrationCutoff, activityPhase } from "../../domain/activity-visibility";
import MainHeader from "../../components/MainHeader.vue";
import ActivityCard from "../../components/ActivityCard.vue";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { utcInput } from "../../services/tournaments";
import { openPage } from "../../utils/navigation";
import { useDiscovery } from "../../stores/discovery";
import { useSession } from "../../stores/session";
import { sortOptions, sortValues, levelOptions, discoveryQuery, ownLevel } from "../../services/discovery";
const location = useDiscovery(), session = useSession();
const mode = ref(0), date = ref(""), ntrp = ref(0), sort = ref(0);
const items = ref<any[]>([]), loading = ref(false), queryError = ref("");
let retryMore = false;
const types = ["全部活动", "全部约球", "自由约球", "定场约球", "比赛"];
const typeValues = ["all", "post", "free", "venue", "tournament"];
let loadVersion = 0;
let page = 1, hasMore = false;
const visibilityNow=ref(Date.now());
let expiryTimer:ReturnType<typeof setTimeout>|undefined, visible=false;
const visibleItems = computed(() => items.value.filter(item=>visibleInDiscovery(item,item.kind,visibilityNow.value)).map(item=>({...item,phase:activityPhase(item,item.kind,visibilityNow.value)})));
function scheduleExpiry() {
  clearTimeout(expiryTimer);visibilityNow.value=Date.now();
  if(!visible)return;
  const future=[...items.value.flatMap(item=>item.kind==="post"?[registrationCutoff(item,"post")]:[registrationCutoff(item,"tournament"),Date.parse(utcInput(item.start_time)),Date.parse(utcInput(item.end_time))])].filter(stamp=>Number.isFinite(stamp)&&stamp>visibilityNow.value);
  const delay=Math.min(future.length?Math.min(...future)-visibilityNow.value+20:2147483647,visibleItems.value.some(t=>t.kind==="tournament" && t.phase==="ongoing")?15000:45000);
  expiryTimer=setTimeout(()=>{visibilityNow.value=Date.now();void load(true);},delay);
}
function stopExpiry(){visible=false;clearTimeout(expiryTimer);loadVersion++;loading.value=false;}
onHide(stopExpiry);onUnload(stopExpiry);
function listingPath(nextPage: number) {
  const extra=discoveryQuery(location.city,sortValues[sort.value],date.value,location.latitude,location.longitude);
  return `/discovery/activities?page=${nextPage}&page_size=20&${extra}&activity_type=${typeValues[mode.value]}${ntrp.value ? "&ntrp_levels="+levelOptions[ntrp.value] : ""}`;
}
async function load(silent = false) {
  const version=++loadVersion, count=silent?Math.max(items.value.length,20):20;
  visibilityNow.value=Date.now();
  if(!silent)items.value=[];
  page=1;hasMore=false;
  if(!location.city){loading.value=false;return;}
  loading.value=true;queryError.value="";
  try {
    let result:PageResult<any>, refreshed:any[]=[];
    do {
      result=await request<PageResult<any>>(listingPath(page));
      if(version!==loadVersion)return;
      refreshed.push(...result.items);
      hasMore=refreshed.length<(result.total||0);
      if(refreshed.length>=count || !hasMore)break;
      page++;
    }while(true);
    items.value=refreshed;
  }catch{if(version===loadVersion){queryError.value="活动暂时无法加载，请稍后重试";retryMore=false;}}
  finally{if(version===loadVersion){loading.value=false;scheduleExpiry();}}
}
async function loadMore() {
  if(loading.value||!hasMore||!location.city)return;
  const version=loadVersion,nextPage=page+1;loading.value=true;queryError.value="";
  try{
    const result=await request<PageResult<any>>(listingPath(nextPage));
    if(version!==loadVersion)return;
    items.value=[...items.value,...result.items];page=nextPage;hasMore=items.value.length<(result.total||0);
  }catch{if(version===loadVersion){queryError.value="暂时无法加载更多活动";retryMore=true;}}
  finally{if(version===loadVersion){loading.value=false;scheduleExpiry();}}
}
function retryQuery(){if(retryMore)void loadMore();else void load();}
function viewTournaments(){mode.value=4;date.value="";ntrp.value=0;void load();}
function clearDate(){date.value="";void load();}
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
  visible=true;visibilityNow.value=Date.now();
  if (!location.city && !location.attempted) { await locateCity(); return; }
  await load();
});
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
onReachBottom(loadMore);
</script>
<template>
  <AppShell active="home">
    <MainHeader title="首页" context @city-change="load()" />
    <view class="content">
      <view class="square-heading"><text>约球广场</text><text class="square-caption">约球 · 比赛</text></view>
      <view class="discovery-filters">
        <view class="filter-line filter-primary">
          <ChoicePicker title="排序方式" :range="sortOptions" :value="sort" @change="sortChange"><view class="filter-control"><text>筛选 · {{ sortOptions[sort].replace('按','') }}</text><wd-icon name="arrow-down" size="12px" /></view></ChoicePicker>
          <ChoicePicker title="活动类型" :range="types" :value="mode" @change="typeChange"><view class="filter-control" :class="{'filter-selected':mode!==0}"><text>{{ types[mode] }}</text><wd-icon name="arrow-down" size="12px" /></view></ChoicePicker>
          <picker mode="date" :value="date" @change="dateChange"><view class="filter-control" :class="{'filter-selected':!!date}"><text>{{ date || '日期' }}</text><wd-icon v-if="date" name="close" size="12px" @click.stop="clearDate" /><wd-icon v-else name="arrow-down" size="12px" /></view></picker>
        </view>
        <view class="filter-line filter-secondary">
          <ChoicePicker title="NTRP 等级" :range="levelOptions" :value="ntrp" @change="levelChange"><view class="filter-control" :class="{'filter-selected':ntrp>0}"><text>{{ ntrp ? 'NTRP '+levelOptions[ntrp] : 'NTRP 等级' }}</text><wd-icon name="arrow-down" size="12px" /></view></ChoicePicker>
          <button class="my-level filter-control" @click="myLevel">适合我的级别</button>
          <button class="view-tournaments filter-control" :class="{selected:mode===4}" @click="viewTournaments">查看比赛</button>
        </view>
      </view>
      <ActivityCard v-for="item in visibleItems" :key="item.kind+'-'+item.id" :item="item" :kind="item.kind" @open="openPage('/pages/common/'+(item.kind==='tournament'?'tournament-detail':'post-detail')+'?id='+item.id)" />
      <view v-if="queryError" class="query-error"><text>{{ queryError }}</text><button @click="retryQuery">重试</button></view>
      <wd-empty v-else-if="!loading && !visibleItems.length" tip="暂无符合筛选的活动" />
      <wd-loading v-if="loading" />
    </view>
  </AppShell>
</template>
<style scoped>
.query-error{display:flex;align-items:center;justify-content:center;gap:8px;padding:20px 8px;color:#7b8c81;font-size:12px}.query-error button{margin:0;padding:4px 10px;line-height:20px;font-size:12px;background:#e9f1eb;color:#286a36;border-radius:8px}.query-error button::after{border:0}
.square-heading{display:flex;align-items:baseline;gap:12px;margin-bottom:14px;font-size:18px;font-weight:700;color:#203c2b}.square-caption{font-size:11px;font-weight:400;color:#7e8e82}
.discovery-filters{margin-bottom:18px;display:flex;flex-direction:column;gap:8px}.filter-line{display:grid;gap:6px;min-width:0}.filter-primary{grid-template-columns:minmax(0,1.18fr) minmax(0,1fr) minmax(0,1.07fr)}.filter-secondary{grid-template-columns:1fr 1.35fr 1.08fr}.filter-line :deep(.choice-select){min-width:0}
.filter-control{display:flex;align-items:center;justify-content:center;gap:4px;min-width:0;box-sizing:border-box;width:100%;height:42px;padding:0 8px;margin:0;border:1px solid #e0e7e2;border-radius:13px;background:linear-gradient(180deg,#fff,#fafcfb);box-shadow:0 2px 5px rgba(33,65,44,.045),inset 0 1px 0 rgba(255,255,255,.8);font-size:12px;font-weight:500;line-height:18px;white-space:nowrap;color:#3d5648}.filter-control text{min-width:0;overflow:hidden;text-overflow:ellipsis}.filter-control::after{border:0}.filter-selected{background:#edf4ee;border-color:#bcd3c1;color:#1d6539;box-shadow:inset 0 0 0 1px rgba(31,102,57,.04)}.my-level{background:linear-gradient(180deg,#eaf3e9,#e1eee2);color:#286a36;border-color:#d3e4d4}.view-tournaments{background:linear-gradient(180deg,#edf7fd,#e1eff9);color:#087fc0;border-color:#ccdfed}.view-tournaments.selected{background:linear-gradient(180deg,#1194d4,#087fba);color:#fff;border-color:#087fba;box-shadow:0 2px 5px rgba(0,117,186,.15)}
@media(max-width:350px){.filter-control{font-size:11px;padding:0 4px;gap:3px;}}
</style>
