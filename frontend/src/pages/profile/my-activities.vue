<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { onLoad, onShow, onHide, onUnload, onReachBottom, onPullDownRefresh } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
import { localTime, teamName, getTournament } from "../../services/tournaments";
import { activityQuery, registrationLabel } from "../../domain/my-activities";
const session = useSession();
const relation = ref("joined"), kind = ref("tournament"), phase = ref("all"), keyword = ref("");
const items = ref<any[]>([]), page = ref(1), more = ref(true), loading = ref(false), failed = ref(false);
const failureMessage = ref("活动暂时无法加载");
const expanded = ref<number | null>(null), personal = ref<any>(null), personalLoading = ref(false), personalError = ref("");
const phaseOptions = computed(() => [{value:"all",label:"全部"},{value:"open",label:"报名中"},{value:"ongoing",label:"进行中"},{value:"ended",label:"已结束"}, ...(relation.value === "joined" ? [{value:"review",label:"待审核"}] : [])]);
const phaseNames: Record<string,string> = { open:"报名中",ongoing:"进行中",ended:"已结束" };
let visible = false, loadVersion = 0, detailVersion = 0, refreshing = false;
let searchTimer: ReturnType<typeof setTimeout> | undefined, refreshTimer: ReturnType<typeof setInterval> | undefined;
onLoad(q => { if (q?.relation === "published") relation.value = "published"; });
async function load(append = false, silent = false) {
  if (!visible || (append && (loading.value || !more.value))) return;
  const version = ++loadVersion, userId = session.user?.id;
  if (!silent) loading.value = true;
  const nextPage = append ? page.value + 1 : 1;
  try {
    const result = await request<PageResult<any>>(activityQuery(kind.value,relation.value,phase.value,keyword.value,nextPage));
    if (version !== loadVersion || !visible || session.user?.id !== userId) return;
    items.value = append ? [...items.value,...result.items] : result.items;
    page.value = nextPage; more.value = items.value.length < (result.total || 0); failed.value = false;
    if (expanded.value != null && !items.value.some(r => r.id === expanded.value)) { expanded.value = null; personal.value = null; detailVersion++; }
  } catch (error: any) {
    if (version === loadVersion && visible) {
      failed.value = true;
      failureMessage.value = error.statusCode === 404 ? "活动查询服务尚未更新，请稍后重试" : (error.message || "活动加载失败");
      if (!silent) uni.showToast({title:failureMessage.value,icon:"none"});
    }
  } finally { if (version === loadVersion) loading.value = false; }
}
function reset() {
  clearTimeout(searchTimer); expanded.value = null; personal.value = null; detailVersion++; items.value = []; more.value = true; void load();
}
function selectRelation(value: string) { if (relation.value === value) return; relation.value = value; phase.value = "all"; reset(); }
function selectPhase(value: string) { if (phase.value === value) return; phase.value = value; reset(); }
function selectKind(e: any) { kind.value = Number(e.detail.value) === 0 ? "tournament" : "post"; reset(); }
function switchActivityType() { kind.value = kind.value === "tournament" ? "post" : "tournament"; phase.value = "all"; keyword.value = ""; reset(); }
watch(keyword, () => { clearTimeout(searchTimer); searchTimer = setTimeout(reset,300); });
async function loadPersonal(silent = false) {
  if (expanded.value == null) return;
  const id = expanded.value, version = ++detailVersion, userId = session.user?.id;
  if (!silent) personalLoading.value = true;
  try {
    const detail = await getTournament(id);
    if (!visible || version !== detailVersion || expanded.value !== id || session.user?.id !== userId) return;
    const provisional = !detail.draw_published && !!detail.participant_preview;
    if (provisional) { detail.teams = detail.participant_preview!.teams; detail.matches = detail.participant_preview!.matches; }
    const position = provisional ? detail.participant_preview?.my_draw : detail.my_draw;
    const mine = detail.teams.find(team => team.user_ids?.includes(userId || ""));
    personal.value = { ...detail, my_draw: position, provisional, personalTeam: mine, personalMatches: position?.matches || [] };
    personalError.value = "";
  } catch (error:any) { if (version === detailVersion && visible) personalError.value = error.message || "对阵暂时无法加载"; }
  finally { if (version === detailVersion) personalLoading.value = false; }
}
function showPersonal(item: any) {
  if (expanded.value === item.id) { expanded.value = null; personal.value = null; detailVersion++; return; }
  expanded.value = item.id; personal.value = null; personalError.value = ""; void loadPersonal();
}
function opponent(match:any) {
  const id = personal.value?.personalTeam?.id || personal.value?.my_draw?.team_id;
  return teamName(personal.value?.teams || [],match.team_a_id === id ? match.team_b_id : match.team_a_id,personal.value?.registrations || []);
}
async function closeActivity(item:any) {
  const result = await uni.showModal({ title: item.kind === "tournament" ? "关闭比赛" : "关闭约球", content: "关闭后停止报名，活动将从广场移除。", editable:item.kind === "tournament", placeholderText:"请填写关闭原因" });
  if (!result.confirm) return;
  const reason = (result.content || "").trim();
  if (item.kind === "tournament" && !reason) return uni.showToast({title:"请填写关闭原因",icon:"none"});
  try {
    await request(item.kind === "tournament" ? `/tournaments/${item.id}/cancel` : `/posts/${item.id}/close`,{method:"POST",data:item.kind === "tournament" ? {reason} : undefined});
    await load();
  } catch (error:any) { uni.showToast({title:error.message || "关闭失败，请重试",icon:"none"}); }
}
function stop() { visible=false; loadVersion++; detailVersion++; clearTimeout(searchTimer); clearInterval(refreshTimer); refreshTimer=undefined; loading.value=false; }
onShow(async () => {
  stop(); visible=true;
  if (!session.requireLogin("/pages/profile/my-activities")) return;
  try { await session.fetchUser(); await load(); }
  catch { failed.value=true; }
  if (visible && session.loggedIn) refreshTimer=setInterval(async () => {
    if (refreshing || loading.value || !visible) return;
    refreshing=true;
    try { if (page.value === 1) await load(false,true); await loadPersonal(true); }
    finally { refreshing=false; }
  },5000);
});
onHide(stop);onUnload(stop);onReachBottom(() => load(true));
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
</script>
<template>
  <AppShell back title="我的活动"><view class="content list-content my-activities">
    <view class="activity-search"><wd-search v-model="keyword" placeholder="搜索活动名称或编号" hide-cancel placeholder-left @search="reset" /></view>
    <view class="relation-tabs"><button :class="{selected:relation === 'joined'}" @click="selectRelation('joined')">我参加的</button><button :class="{selected:relation === 'published'}" @click="selectRelation('published')">我发布的</button></view>
    <view class="activity-filters"><scroll-view scroll-x class="phase-scroll"><view class="phase-options"><button v-for="option in phaseOptions" :key="option.value" class="filter-pill" :class="{selected:phase === option.value}" @click="selectPhase(option.value)">{{ option.label }}</button></view></scroll-view><picker :range="['比赛','约球']" :value="kind === 'tournament' ? 0 : 1" @change="selectKind"><view class="type-filter">筛选 · {{ kind === 'tournament' ? '比赛' : '约球' }}<wd-icon name="arrow-down" size="12px" /></view></picker></view>
    <view v-for="item in items" :key="item.id" class="record-card activity-card">
      <view class="activity-main" @click="openPage(`/pages/common/${item.kind === 'tournament' ? 'tournament' : 'post'}-detail?id=${item.id}`)"><Photo :src="item.cover_image" width="72px" height="80px" fallback="/static/tennis.jpg" /><view class="activity-copy"><view class="row between"><text class="muted small">{{ item.kind === 'tournament' ? '比赛' : '约球' }} · #{{ item.id }}</text><text class="tag">{{ ['cancelled','closed'].includes(item.status) ? '已关闭' : phaseNames[item.phase] }}</text></view><text class="activity-title">{{ item.title }}</text><text class="muted small">{{ item.kind === 'tournament' ? localTime(item.start_time) : `${item.preferred_date || '时间待定'} ${item.preferred_start || ''}` }}</text><text v-if="item.address" class="muted small">{{ item.address }}</text></view></view>
      <view v-if="relation === 'joined' && item.registration" class="registration-line"><text class="registration-state" :class="{pending:registrationLabel(item) === '待审核'}">{{ registrationLabel(item) }}</text><text v-if="item.registration.review_reason" class="muted small">{{ item.registration.review_reason }}</text></view>
      <view class="row activity-actions"><wd-button v-if="relation === 'joined' && item.kind === 'tournament'" size="small" variant="text" @click="showPersonal(item)">{{ expanded === item.id ? '收起我的对阵' : '我的分组与对阵' }}</wd-button><template v-if="relation === 'published' && item.can_manage"><wd-button size="small" variant="text" @click="openPage(`/pages/profile/applications?kind=${item.kind}`)">处理报名</wd-button><wd-button v-if="item.kind === 'tournament' && item.phase !== 'ended'" size="small" variant="text" @click="openPage(`/pages/publish/tournament-create?id=${item.id}`)">编辑比赛</wd-button><wd-button v-if="item.phase !== 'ended'" size="small" variant="plain" @click="closeActivity(item)">关闭{{ item.kind === 'tournament' ? '比赛' : '约球' }}</wd-button></template></view>
      <view v-if="expanded === item.id" class="personal-detail"><text v-if="personalLoading" class="muted small">正在加载对阵…</text><view v-else-if="personalError"><text class="muted small">{{ personalError }}</text><wd-button size="small" variant="text" @click="loadPersonal()">重试</wd-button></view><template v-else-if="personal"><text class="muted small">{{ personal.provisional ? '临时预览 · 正式对阵以发布签表为准' : ('签表 v' + personal.published_version) }}</text><text class="strong small">{{ personal.my_draw ? `第 ${personal.my_draw.group_no} 组 · ${personal.my_draw.half}` : item.registration.requested_group ? `第 ${item.registration.requested_group} 组 · 待发布签表` : '自动分组 · 待发布签表' }}</text><view v-for="match in personal.personalMatches" :key="match.key" class="personal-match"><text>第 {{ match.round_no }} 轮 · 对手：{{ opponent(match) }}</text><text class="muted small">{{ match.status === 'bye' ? '轮空晋级' : match.score || '待比赛' }} · {{ localTime(match.scheduled_at) }} · {{ match.court || '待排场' }}</text></view><text v-if="!personal.personalMatches.length" class="muted small">报名确认并完成抽签后，可查看自己的对阵。</text></template></view>
    </view>
    <view v-if="failed" class="empty-state"><text class="muted">{{ failureMessage }}</text><wd-button size="small" @click="load()">重试</wd-button></view><wd-empty v-else-if="!loading && !items.length" :tip="keyword || phase !== 'all' ? '当前筛选无结果' : `暂无${relation === 'published' ? '发布' : '参加'}的${kind === 'tournament' ? '比赛' : '约球'}`"><template #bottom><view class="empty-type-action"><text @click="switchActivityType">查看{{ kind === 'tournament' ? '约球' : '比赛' }}记录</text></view></template></wd-empty><text v-if="loading" class="muted loading-text">正在加载…</text>
  </view></AppShell>
</template>
<style scoped>
.empty-type-action{margin-top:16px;text-align:center;font-size:14px;color:#147553}

.activity-search{overflow:hidden;border:1px solid var(--playnow-card-border);border-radius:var(--playnow-card-radius);background:white;margin-bottom:22px;--wot-search-input-height:44px;--wot-search-input-font-size:15px}.relation-tabs{display:flex;padding:4px;border:1px solid var(--playnow-card-border);border-radius:12px;background:#fff;margin-bottom:16px}.relation-tabs button{flex:1;border:0;background:transparent;font-size:15px;font-weight:600;color:#87968b;line-height:42px;margin:0;border-radius:9px}.relation-tabs button::after,.phase-options button::after{border:0}.relation-tabs button.selected{background:#147553;color:white}.activity-filters{display:flex;align-items:center;gap:10px;margin-bottom:20px}.phase-scroll{flex:1;min-width:0;white-space:nowrap}.phase-options{display:flex;gap:8px}.phase-options button{flex-shrink:0;margin:0;padding:8px 12px;font-size:13px;line-height:20px}.filter-pill.selected{background:#e8f1eb;border-color:#147553;color:#147553}.type-filter{display:flex;align-items:center;gap:6px;white-space:nowrap;background:#fff;border:1px solid var(--playnow-card-border);border-radius:10px;padding:10px;font-size:13px;color:#304238}.activity-main{display:flex;gap:14px}.activity-copy{min-width:0;flex:1}.activity-title{display:block;margin:8px 0;font-size:16px;line-height:1.5;font-weight:600}.activity-copy .small{display:block;line-height:1.6}.activity-copy .row .small{display:inline}.activity-copy .tag{white-space:nowrap;font-size:11px}.registration-line{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:16px;border-top:1px solid var(--playnow-card-border);padding-top:12px}.registration-state{font-size:13px;color:#147553}.registration-state.pending{color:#9e7935}.activity-actions{justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-top:8px}.activity-actions:empty{display:none}.personal-detail{border-top:1px solid var(--playnow-card-border);margin-top:12px;padding-top:12px;display:flex;flex-direction:column;gap:8px}.personal-match{padding-top:10px;font-size:13px;line-height:1.6}.personal-match text{display:block}.loading-text{display:block;text-align:center;padding:20px}
</style>
