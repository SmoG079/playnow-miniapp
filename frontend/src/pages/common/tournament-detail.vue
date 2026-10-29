<script setup lang="ts">
import ChoiceSelect from "../../components/ChoiceSelect.vue";
import { paymentLabel, registrationNotice } from "../../domain/activity-payment";
import ParticipantIdentity from "../../components/ParticipantIdentity.vue";
import { cardState } from "../../domain/activity-card";
import { drawBlockReason } from "../../domain/draw-readiness";
import { computed, reactive, ref, nextTick } from "vue";
import TournamentEntryTeams from "../../components/TournamentEntryTeams.vue";
import {
  onLoad,
  onShow,
  onHide,
  onUnload,
  onShareAppMessage,
  onShareTimeline,
} from "@dcloudio/uni-app";
import { sharedActivityId } from "../../services/activity-sharing";
import ActivityFacts from "../../components/ActivityFacts.vue";
import { cardSchedule } from "../../domain/activity-card";
import ActivityShare from "../../components/ActivityShare.vue";
import { activityShare, enableActivitySharing, isTimelinePreview, guideToMiniProgram } from "../../utils/share";
import AppShell from "../../components/AppShell.vue";
import TournamentDrawEditor from "../../components/TournamentDrawEditor.vue";
import TournamentBracket from "../../components/TournamentBracket.vue";
import TournamentSchedulePreview from "../../components/TournamentSchedulePreview.vue";
import {
  buildSchedulePreview,
  personalDraw,
} from "../../services/tournament-preview";
import { request } from "../../services/api";
import { payTournament } from "../../services/payment";
import { useSession } from "../../stores/session";
import { tournamentPollDelay } from "../../domain/activity-polling";
import {
  getTournament,
  command,
  localTime,
  utcInput,
  teamName,
  formatNames,
  disciplineNames,
  type Tournament,
  type Match,
  type Registration,
  type EntryTeam,
} from "../../services/tournaments";
const s = useSession(),
  id = ref(0),
  t = ref<Tournament | null>(null),
  busy = ref(false),
  tab = ref("intro"),
  error = ref(""),
  invite = ref(""),
  popup = ref(false),
  edit = ref<"result" | "schedule" | "tie">("result"),
  selected = ref<Match | null>(null),
  historyVersion = ref(0),
  history = ref<any>(null),
  mineOnly = ref(false);
const contactingOrganizer = ref(false);
async function contactOrganizer() {
  if (t.value?.club_id) {
    if (t.value.contact_phone) uni.makePhoneCall({phoneNumber:t.value.contact_phone});
    return;
  }
  if (!s.requireLogin(`/pages/common/tournament-detail?id=${id.value}`) || contactingOrganizer.value) return;
  contactingOrganizer.value = true;
  try {
    const c = await request<{id:string}>('/messages/conversations',{method:'POST',data:{activity_id:id.value}});
    uni.navigateTo({url:'/pages/chat/conversation?id='+c.id});
  } catch(e:any) { uni.showToast({title:e.message || '暂时无法联系主办方',icon:'none'}); }
  finally { contactingOrganizer.value = false; }
}
const showCancelledRecords = ref(false);
const cancelledRegistrations = computed(() => (t.value?.registrations||[]).filter(r=>r.status==="cancelled" || r.admission==="cancelled"));
const managementRegistrations = computed(() => (t.value?.registrations||[]).filter(r=>showCancelledRecords.value || !(r.status==="cancelled" || r.admission==="cancelled")));
const adjustingDraw = ref(false);
async function saveDrawAdjustment(data:any) {
  try { await run("draw/adjust",data); adjustingDraw.value=false; uni.showToast({title:"调整已保存，请重新发布",icon:"none"}); }
  catch(e:any) { uni.showModal({title:"保存调整失败",content:e.message||"请刷新后重试",showCancel:false}); }
}
const previewOpen = ref(false),
  schedulePreview = ref<ReturnType<typeof buildSchedulePreview> | null>(null);
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let refreshing = false;
let visible = false;
let loadVersion = 0;
const myPosition = computed(() =>
  personalDraw(
    t.value?.teams?.length
      ? t.value.teams
      : t.value?.participant_preview?.teams || [],
    t.value?.matches?.length
      ? t.value.matches
      : t.value?.participant_preview?.matches || [],
    s.user?.id,
  ),
);
const registration = reactive({
  entry_team_id: null as number | null,
  entry_seat: null as number | null,
  requested_group: 0,
  gender: "" as "" | "male" | "female",
});
const form = reactive({
  winner: 0,
  score: "",
  reason: "",
  is_draw: false,
  walkover: false,
  court: "",
  date: "",
  time: "",
  group: "1",
  order: "",
});
const mine = computed(() => t.value?.my_registration),
  cfg = computed(() => t.value?.config);
const stateNames: Record<string, string> = {
  active: "正式名额",
  waitlisted: "候补",
  review: "待审核",
  expired: "名额已过期",
  cancelled: "已取消",
  rejected: "未通过审核",
  pending: "待处理",
  approved: "审核通过",
  paid: "已支付",
  none: "免费",
  verified: "已核验",
  unverified: "历史付款待核验",
  confirmed: "已确认",
  offline: "线下付款",
  registered: "报名中",
  processing: "退款处理中",
  success: "退款成功",
  failed: "退款失败",
  abnormal: "退款异常",
  closed: "退款关闭",
};
const viewData = computed(() => history.value || t.value);
const shownMatches = computed(() => {
  const ms: Match[] = viewData.value?.matches?.length
    ? viewData.value.matches
    : t.value?.participant_preview?.matches || [];
  return mineOnly.value
    ? ms.filter((m) =>
        [m.team_a_id, m.team_b_id].some((i) =>
          viewData.value?.teams
            .find((x: any) => x.id === i)
            ?.user_ids?.includes(s.user?.id),
        ),
      )
    : ms;
});
const canJoin = computed(
  () =>
    !mine.value ||
    ["cancelled", "expired", "rejected"].includes(mine.value.admission || ""),
);
const title = computed(() =>
  !s.loggedIn
    ? "登录后报名"
    : !canJoin.value
      ? stateNames[mine.value?.admission || ""] || "已报名"
      : !t.value?.can_register
        ? "报名已关闭"
        : Number(t.value.entry_fee) > 0
          ? `报名 ¥${t.value.entry_fee}`
          : "立即报名",
);
async function load() {
  const version = ++loadVersion;
  try {
    const result = await getTournament(id.value);
    if (version !== loadVersion || !visible) return;
    t.value = result;
    error.value = "";
    if (previewOpen.value) showSchedulePreview();
  } catch (e) {
    if (version !== loadVersion || !visible) return;
    error.value = "赛事加载失败，请重试";
  } finally {
    if (version === loadVersion) scheduleRefresh();
  }
}
onLoad((q) => {
  id.value = Number(sharedActivityId(q));
  enableActivitySharing();
  invite.value = String(q?.invite || "");
  void s.fetchUser().catch(() => {});
});
function stopRefresh() {
  visible = false;
  loadVersion++;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = undefined;
}
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = undefined;
  const delay = tournamentPollDelay(t.value);
  if (!visible || !id.value || delay === null) return;
  refreshTimer = setTimeout(async () => {
    if (!visible) return;
    if (busy.value || refreshing || adjustingDraw.value) { scheduleRefresh(); return; }
    refreshing = true;
    try {
      await load();
    } finally {
      refreshing = false;
    }
  }, delay);
}
onShow(() => {
  stopRefresh();
  visible = true;
  if (id.value) void load();
});
onHide(stopRefresh);
onUnload(stopRefresh);
function showSchedulePreview() {
  if (!cfg.value || !t.value) return;
  try {
    schedulePreview.value = buildSchedulePreview(
      cfg.value,
      t.value.max_participants,
      t.value.start_time,
      t.value.end_time,
    );
    const live = t.value.matches.length ? t.value : t.value.participant_preview;
    if (live?.matches.length) {
      schedulePreview.value = {
        ...schedulePreview.value,
        teams: live.teams,
        matches: live.matches,
        total_matches: live.matches.filter((m) => m.status !== "bye").length,
        rounds: Math.max(...live.matches.map((m) => m.round_no)),
        knockout_preview: undefined,
        note: t.value.draw_published ? "当前正式赛程，比分自动更新" : "临时对阵，正式对阵以发布签表为准",
      };
    }
    previewOpen.value = true;
  } catch (e: any) {
    uni.showToast({ title: e.message || "无法生成预览", icon: "none" });
  }
}
async function changeGroup(group: number) {
  await run("group", { requested_group: group });
}

onShareAppMessage((event) => activityShare("tournament", id.value, t.value?.title, t.value?.cover_image,
  event.from === "button" && event.target?.dataset?.shareKind === "partner" ? mine.value?.invite_token || undefined : undefined));
onShareTimeline(() => {
  const { title, query, imageUrl } = activityShare("tournament", id.value, t.value?.title, t.value?.cover_image);
  return { title, query, imageUrl };
});
function name(ident?: number | null) {
  return teamName(
    viewData.value?.teams?.length
      ? viewData.value.teams
      : t.value?.participant_preview?.teams || [],
    ident,
    t.value?.registrations || [],
  );
}
async function run(
  path: string,
  data?: unknown,
  method: "POST" | "PUT" = "POST",
) {
  if (busy.value) return;
  busy.value = true;
  try {
    const result = await command(id.value, path, data, method);
    await load();
    return result;
  } finally {
    busy.value = false;
  }
}
async function reason(message: string) {
  const r = await uni.showModal({
    title: message,
    editable: true,
    placeholderText: "填写原因",
    content: "",
  });
  return r.confirm ? r.content?.trim() : undefined;
}
async function confirm(message: string) {
  return (await uni.showModal({ title: "确认操作", content: message })).confirm;
}
async function join() {
  if (
    !s.requireLogin(
      `/pages/common/tournament-detail?id=${id.value}${invite.value ? "&invite=" + invite.value : ""}`,
    )
  )
    return;
  if (!t.value?.can_register || !canJoin.value) return;
  if (cfg.value?.pairing === 'fixed' && !registration.entry_team_id) {
    tab.value = 'players';
    await nextTick();
    uni.pageScrollTo({selector:'.entry-roster',duration:250});
    uni.showToast({title:'请选择队伍中的空位报名',icon:'none'});
    return;
  }
  if (cfg.value?.discipline === "mixed" && !registration.gender) {
    uni.showToast({ title: "请选择报名性别", icon: "none" });
    return;
  }
  const text = registrationNotice(t.value.entry_fee, t.value.payment_method || "online");
  if (!(await confirm(text))) return;
  const r = await run("register", {
    requested_group: registration.requested_group,
    gender: registration.gender || null,
    entry_team_id: registration.entry_team_id,
    entry_seat: registration.entry_seat,
  });
  registration.entry_team_id = registration.entry_seat = null;
  if (r?.payment === "pending") await pay();
}
async function chooseEntrySeat(team: EntryTeam, seat: EntryTeam['seats'][number]) {
  if (!s.requireLogin(`/pages/common/tournament-detail?id=${id.value}`)) return;
  if (seat.occupied || busy.value || !t.value?.can_register) return;
  try {
    if (!canJoin.value) {
      if (await confirm(`更换到第${team.group_no}组${team.position}队？原有搭档关系会解除。`)) {
        await run('team-seat',{entry_team_id:team.id,entry_seat:seat.seat});
      }
      return;
    }
    registration.entry_team_id = team.id;
    registration.entry_seat = seat.seat;
    registration.requested_group = team.group_no;
    if (seat.gender) registration.gender = seat.gender;
    await join();
  } catch(e:any) {
    uni.showToast({title:e.message || '报名失败，请重试',icon:'none'});
    await load();
  } finally { registration.entry_team_id = registration.entry_seat = null; }
}
async function pay() {
  busy.value = true;
  try {
    await payTournament(id.value);
    uni.showToast({ title: "支付确认中", icon: "none" });
    await command(id.value, "payment-status");
    await load();
  } finally {
    busy.value = false;
  }
}
async function cancelReg(r: Registration) {
  const why = await reason(t.value?.payment_method === "offline" ? "取消报名（线下费用请与组织者协商）" : "取消报名（截止前全额退）");
  if (why) await run(`registrations/${r.id}/cancel`, { reason: why });
}
async function review(r: Registration, approved: boolean) {
  const why = await reason(approved ? "通过报名审核" : "拒绝报名");
  if (why) await run(`registrations/${r.id}/review`, { reason: why, approved });
}
async function accept() {
  if (!s.requireLogin()) return;
  try {
    if (canJoin.value) {
      const spot = await request<{entry_team_id:number;entry_seat:number}>(`/tournaments/${id.value}/invitations/${invite.value}`);
      const team = t.value?.entry_teams.find(team=>team.id === spot.entry_team_id);
      const seat = team?.seats.find(seat=>seat.seat === spot.entry_seat);
      if (!team || !seat) throw new Error('队伍席位已变化，请刷新后重试');
      await chooseEntrySeat(team,seat);
      if (mine.value?.entry_team_id === team.id) invite.value = '';
      return;
    }
    await run(`invitations/${invite.value}/accept`);
    invite.value = "";
    uni.showToast({ title: "搭档已确认", icon: "success" });
  } catch(e:any) {
    uni.showToast({title:e.message || '无法加入搭档队伍',icon:'none'});
  }
}
async function draw(stage = "initial") {
  if(stage === "initial" && drawBlockReason(t.value)) {
    uni.showModal({title:"暂不能抽签",content:drawBlockReason(t.value),showCancel:false});return;
  }
  if (t.value?.draw_stage === "knockout") stage = "knockout";
  let why = "";
  if (
    t.value?.draw_version &&
    (stage === "initial" || t.value.draw_stage === "knockout")
  ) {
    why = (await reason("重新抽签并发布（保留历史版本）")) || "";
    if (!why) return;
  }
  const redrawing =
    !!t.value?.draw_version &&
    (stage === "initial" || t.value.draw_stage === "knockout");
  const hasResults =
    redrawing && t.value?.matches.some((m) => m.status === "completed");
  if (
    hasResults &&
    !(await confirm(
      "重新抽签会归档当前结果并发布新的签表，旧签表与比分保留在历史版本中。确定继续？",
    ))
  )
    return;
  try {
    const r = await run("draw", {
      archive_results: !!hasResults,
      publish: redrawing,
      stage,
      reason: why,
      expected_version: t.value?.draw_version || 0,
      idempotency_key: `draw-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    });
    if (r?.overflows)
      uni.showModal({ title: "需调整排场", content: r.note, showCancel: false });
  } catch (err) {
    uni.showModal({
      title: redrawing ? "重新抽签失败" : "生成抽签失败",
      content:
        err instanceof Error && err.message
          ? err.message
          : "抽签失败，请稍后重试",
      showCancel: false,
      confirmText: "知道了",
    });
  }
}
async function reopenRegistration() {
  if (!(await confirm("重新开放报名并解除名单冻结？抽签前可继续补充参赛者。"))) return;
  try { await run("reopen-registration"); }
  catch(e:any) { uni.showModal({title:"重新开放报名失败",content:e.message||"请刷新后重试",showCancel:false}); }
}
async function publish() {
  if (await confirm("发布后所有用户将看到当前正式签表"))
    await run("draw/publish", { expected_version: t.value?.draw_version });
}
function openEdit(m: Match, mode: "result" | "schedule") {
  selected.value = m;
  edit.value = mode;
  Object.assign(form, {
    winner: m.winner_id || m.team_a_id || 0,
    score: m.score || "",
    reason: "",
    is_draw: m.is_draw || false,
    walkover: m.walkover || false,
    court: m.court || cfg.value?.courts[0] || "",
    date: localTime(m.scheduled_at || t.value?.start_time).slice(0, 10),
    time: localTime(m.scheduled_at || t.value?.start_time).slice(11),
  });
  popup.value = true;
}
async function submitEdit() {
  if (edit.value === "tie")
    await run("tie-order", {
      expected_version: t.value?.draw_version,
      group_no: Number(form.group),
      team_ids: form.order
        .split(/[,，\s]+/)
        .filter(Boolean)
        .map(Number),
      reason: form.reason,
    });
  else if (edit.value === "result")
    await run(
      `matches/${selected.value?.id}/result`,
      {
        expected_version: t.value?.draw_version,
        winner_id: form.is_draw ? null : form.winner,
        is_draw: form.is_draw,
        score: form.score,
        walkover: form.walkover,
        reason: form.reason,
      },
      "PUT",
    );
  else
    await run(
      `matches/${selected.value?.id}/schedule`,
      {
        expected_version: t.value?.draw_version,
        court: form.court,
        start_time: new Date(
          `${form.date}T${form.time}:00+08:00`,
        ).toISOString(),
      },
      "PUT",
    );
  popup.value = false;
}
async function reset(m: Match) {
  const why = await reason("撤销比赛结果");
  if (why)
    await run(`matches/${m.id}/reset`, {
      expected_version: t.value?.draw_version,
      reason: why,
    });
}
async function verifyLegacy(r: Registration) {
  const why = await reason("核验历史报名资格（不生成收款记录）");
  if (why) await run(`registrations/${r.id}/verify-payment`, { reason: why });
}
async function refund(r: Registration) {
  const why = await reason("管理员全额退款");
  if (why) await run(`registrations/${r.id}/refund`, { reason: why });
}
async function cancelEvent() {
  const why = await reason("取消整个赛事并全额退款");
  if (why && (await confirm("所有参赛名额将取消，已支付订单将原路退款")))
    await run("cancel", { reason: why });
}
async function finish() {
  if (await confirm("确认所有比赛已完成并结束赛事？"))
    await run("finish", { expected_version: t.value?.draw_version });
}
async function selectHistory(v: number) {
  historyVersion.value = v;
  if (v === t.value?.draw_version) history.value = null;
  else history.value = await request(`/tournaments/${id.value}/draws/${v}`);
}
function tie() {
  edit.value = "tie";
  form.reason = "";
  form.order = "";
  form.group = "1";
  popup.value = true;
}
</script>
<template>
  <AppShell back title="赛事详情">
    <view v-if="error" class="content empty-state">
      <wd-icon name="info-circle" size="44px" color="#728178" />
      <text class="section-title">赛事信息加载失败</text>
      <text class="muted">请检查网络后重新加载</text>
      <wd-button size="small" @click="load">重新加载</wd-button>
    </view>
    <template v-else-if="t">
      <Photo
        width="100%"
        height="230px"
        :src="t.cover_image"
        fallback="/static/tennis.jpg"
        mode="aspectFill"
      />
      <view class="content tournament-content"
        ><text class="page-title">{{ t.title }}</text
        ><text class="tag">{{ cardState(t, null, "tournament").label }}</text
        ><text class="tag">{{
          cfg
            ? formatNames[cfg.format] + " · " + disciplineNames[cfg.discipline]
            : "赛事"
        }}</text
        ><ActivityFacts :schedule="cardSchedule({start_time:t.start_time,end_time:t.end_time},'tournament').dateLabel + ' ' + cardSchedule({start_time:t.start_time,end_time:t.end_time},'tournament').timeLabel" :name="t.location_name || '地点名称待补充'" :address="t.address" :can-navigate="t.latitude != null && t.longitude != null" @navigate="uni.openLocation({latitude:Number(t.latitude),longitude:Number(t.longitude),name:t.location_name,address:t.address})" />
        <text class="muted small">已报名 {{ t.current_participants }}/{{ t.max_participants }} 人</text>
        <view v-if="myPosition" class="list-card"
          ><text class="strong"
            >我的比赛：第 {{ myPosition.team.group_no }} 组 ·
            {{ myPosition.half }}</text
          ><text class="muted">{{
            t.draw_version
              ? "签表 v" + t.draw_version
              : "临时对阵预览，正式对阵以发布签表为准"
          }}</text
          ><view v-for="m in myPosition.matches" :key="m.key" class="my-match"
            ><text
              >{{
                m.team_a_id === myPosition.team.id ||
                m.team_b_id === myPosition.team.id
                  ? name(
                      m.team_a_id === myPosition.team.id
                        ? m.team_b_id
                        : m.team_a_id,
                    )
                  : "待晋级后确定对手"
              }}
              ·
              {{ m.status === "bye" ? "轮空晋级" : m.score || "待比赛" }}</text
            ><text class="muted"
              >第 {{ m.round_no }} 轮 · {{ localTime(m.scheduled_at) }} ·
              {{ m.court || "待排场" }}</text
            ></view
          ><wd-button size="small" variant="plain" @click="tab = 'bracket'"
            >查看我的比赛</wd-button
          ></view
        >
        <wd-button v-if="cfg" block variant="plain" @click="showSchedulePreview"
          >预览赛程结构</wd-button
        >
        <wd-tabs v-model="tab"
          ><wd-tab title="介绍" name="intro">
            <view class="pane intro-pane">
              <view class="intro-section"><text class="intro-heading">赛事介绍</text><text class="intro-copy">{{ t.description || '欢迎报名参加本次赛事' }}</text></view>
              <view v-if="t.prizes.length" class="intro-section prizes-section">
                <text class="intro-heading">奖项设置</text>
                <view v-for="(prize,i) in t.prizes" :key="i" class="prize-row">
                  <view class="prize-name"><wd-icon name="trophy" size="16px" color="#0787c8" /><text>{{ prize.name }}</text></view>
                  <text v-if="prize.description" class="prize-description">{{ prize.description }}</text>
                </view>
              </view>
              <view v-if="t.images?.length" class="intro-section"><text class="intro-heading">赛事图片</text><view class="gallery"><Photo v-for="img in t.images" :key="img" :src="img" width="100%" height="180px" /></view></view>
              <view class="intro-section"><text class="intro-heading">主办与联系</text><view class="organizer-profile"><Photo :src="t.club_id ? t.club_avatar : t.organizer_avatar" width="44px" height="44px" round /><view class="organizer-copy"><text class="organizer-name">{{ t.club_id ? t.club_name : t.organizer_nickname || '球友' }}</text><text class="organizer-type">{{ t.club_id ? '俱乐部主办' : '个人主办' }}</text></view></view><text v-if="t.club_id && t.contact_name" class="intro-copy">联系人：{{ t.contact_name }}</text><wd-button v-if="t.club_id ? !!t.contact_phone : !!t.organizer_user_id && t.organizer_user_id !== s.user?.id" size="small" variant="plain" :loading="contactingOrganizer" @click="contactOrganizer">联系主办方</wd-button></view>
              <view class="intro-section registration-section"><text class="intro-heading">报名须知</text><text class="intro-copy">NTRP 等级：{{ t.level_required || '不限' }}</text><text class="intro-copy">报名截止：{{ localTime(t.registration_deadline) }}</text><text class="intro-copy">自助取消截止：{{ localTime(t.cancellation_deadline) }}</text><text class="intro-copy">付款方式：{{ paymentLabel(t.entry_fee, t.payment_method || 'online') }}</text><text class="muted small">{{ Number(t.entry_fee) <= 0 ? '本次比赛免费参加。' : t.payment_method === 'offline' ? '报名无需线上支付，费用由组织者线下收取；退费请与组织者协商。' : '截止前全额原路退款，之后由管理员处理；主办方取消全退。' }}</text></view>
            </view>
          </wd-tab>
          <wd-tab title="参与者" name="players"><view class="pane">
            <TournamentEntryTeams :teams="t.entry_teams" :ungrouped="cfg?.ungrouped_display" :selectable="cfg?.pairing === 'fixed' && t.can_register && !t.roster_frozen" :my-user-id="s.user?.id" :busy="busy" @select="chooseEntrySeat" />
          </view></wd-tab>
          <wd-tab title="赛程" name="bracket"
            ><view class="pane"
              ><text class="muted">{{
                t.draw_published ? "正式签表" : "待发布；管理员看到的为抽签草稿"
              }}</text
              ><wd-button v-if="t.can_adjust_draw && !adjustingDraw && !history" variant="plain" :disabled="busy" @click="adjustingDraw=true">调整对位</wd-button>
              <TournamentDrawEditor v-if="adjustingDraw" :tournament="t" :busy="busy" @cancel="adjustingDraw=false" @save="saveDrawAdjustment" />
              <view class="choices"
                ><wd-button
                  v-for="h in t.history"
                  :key="h.version"
                  size="small"
                  variant="plain"
                  @click="selectHistory(h.version)"
                  >{{ h.stage === "knockout" ? "淘汰阶段" : "初始阶段" }} v{{
                    h.version
                  }}</wd-button
                ></view
              ><TournamentBracket
                :teams="
                  viewData?.teams?.length
                    ? viewData.teams
                    : t.participant_preview?.teams ||
                      t.bracket_preview?.teams ||
                      []
                "
                :matches="
                  viewData?.matches?.length
                    ? viewData.matches
                    : t.participant_preview?.matches ||
                      t.bracket_preview?.matches ||
                      []
                "
                :registrations="t.registrations"
                :my-user-id="s.user?.id" /></view
          ></wd-tab>
          <wd-tab title="排名" name="ranking"
            ><view class="pane"
              ><text v-if="!viewData?.rankings?.length" class="muted"
                >比赛开始后生成排名</text
              ><view
                v-for="r in viewData?.rankings || []"
                :key="r.team_id"
                class="list-card"
                ><text
                  >第 {{ r.group_no }} 组 · {{ r.rank || "待定" }}名 ·
                  {{ name(r.team_id) }}</text
                ><text class="muted"
                  >{{ r.points != null ? "积分 " + r.points : "" }}
                  {{ r.tie_unresolved ? "同分顺序待管理员确认" : "" }}</text
                ></view
              ></view
            ></wd-tab
          ></wd-tabs
        >
        <view v-if="mine" class="list-card"
          ><text class="muted"
            >报名组别：{{
              mine.requested_group
                ? "第 " + mine.requested_group + " 组"
                : "自动分组"
            }}</text
          ><ChoiceSelect
            v-if="cfg && cfg.pairing !== 'fixed' && cfg.group_count > 1 && !t.roster_frozen && !canJoin && !mine.partner_user_id"
            :model-value="mine.requested_group || 0" title="更换参赛组" :disabled="busy"
            :options="[{value:0,label:'自动分组'},...(t.registration_groups || []).map(g=>({value:g.group_no,label:'第 '+g.group_no+' 组',description:g.reserved+'/'+g.capacity+' 人已占位'}))]"
            @change="changeGroup(Number($event))" />
          <text>我的报名：{{ stateNames[mine.admission || ""] }}</text
          ><text class="muted"
            >{{ stateNames[mine.approval || ""] }} ·
            {{ stateNames[mine.payment || ""] }}</text
          ><text v-if="mine.seat_expires_at" class="muted"
            >支付期限：{{ localTime(mine.seat_expires_at) }}</text
          ><text v-if="mine.review_reason" class="muted"
            >审核说明：{{ mine.review_reason }}</text
          ><text v-if="mine.refund_status" class="muted">{{
            stateNames[mine.refund_status] || mine.refund_status
          }}</text>
          <view class="choices"
            ><wd-button
              v-if="mine.payment === 'pending' && mine.admission === 'active'"
              size="small"
              :loading="busy"
              @click="pay"
              >去支付</wd-button
            ><wd-button
              v-if="mine.payment === 'pending'"
              size="small"
              variant="plain"
              @click="run('payment-status')"
              >刷新支付状态</wd-button
            ><wd-button
              v-if="!t.roster_frozen && !canJoin"
              size="small"
              variant="plain"
              @click="cancelReg(mine)"
              >取消报名</wd-button
            ></view
          >
          <template
            v-if="
              cfg?.pairing === 'fixed' &&
              cfg &&
              !t.roster_frozen &&
              !canJoin
            "
            ><text class="muted">{{
              mine.partner_user_id
                ? "搭档已确认"
                : cfg.pairing === "fixed"
                  ? "待确认搭档"
                  : "随机搭档，抽签时配对"
            }}</text
            ><view class="choices"
              ><button
                v-if="mine.invite_token"
                open-type="share"
                data-share-kind="partner"
                class="share-button"
              >
                分享搭档邀请
              </button></view
            ></template
          >
        </view>
        <view v-if="invite" class="list-card"
          ><text>你收到一个搭档邀请。双方须各自完成报名；费用按本次比赛的付款方式处理。</text
          ><wd-button block :loading="busy" @click="accept"
            >确认搭档邀请</wd-button
          ></view
        >
        <view v-if="canJoin && t.can_register && cfg?.pairing !== 'fixed'" class="list-card"
          ><ChoiceSelect v-if="cfg && cfg.group_count > 1" v-model="registration.requested_group" title="参赛组" :options="[
            {value:0,label:'自动分组',description:'由系统安排组别，抽签保持已确定的组别。'},
            ...(t.registration_groups || []).map(g=>({value:g.group_no,label:'第 '+g.group_no+' 组',description:g.reserved+'/'+g.capacity+' 人已占位'}))
          ]" />
          <ChoiceSelect v-if="cfg?.discipline === 'mixed'" v-model="registration.gender" title="报名性别" :options="[{value:'male',label:'男'},{value:'female',label:'女'}]" />
          </view
        >
        <view v-if="t.can_manage" class="manager"
          ><text class="section-title">赛事管理</text>
          <view class="choices"
            ><wd-button
              v-if="!t.roster_frozen && !t.draw_version"
              size="small"
              variant="plain"
              @click="
                uni.navigateTo({
                  url: '/pages/publish/tournament-create?id=' + id,
                })
              "
              >编辑配置</wd-button
            ><wd-button
              v-if="!t.roster_frozen"
              size="small"
              :loading="busy"
              @click="
                confirm('关闭报名并冻结名单？').then(
                  (ok) => ok && run('close-registration'),
                )
              "
              >关闭报名</wd-button
            ><wd-button v-if="t.roster_frozen && !t.draw_version && t.status === 'open'" size="small" variant="plain" :loading="busy" :disabled="Date.now() >= new Date(utcInput(t.registration_deadline || t.start_time)).getTime()" @click="reopenRegistration">重新开放报名</wd-button><wd-button
              v-if="
                cfg &&
                t.roster_frozen &&
                t.status !== 'finished' &&
                t.status !== 'cancelled'
              "
              size="small"
              :loading="busy"
              :disabled="!!drawBlockReason(t)"
              custom-class="draw-draft-button"
              @click="draw()"
              >{{ t.draw_version ? "重新抽签" : "生成抽签草稿" }}</wd-button
            ><text v-if="t.roster_frozen && drawBlockReason(t)" class="muted small">{{drawBlockReason(t)}}</text><wd-button
              v-if="t.draw_version && !t.draw_published"
              size="small"
              :loading="busy"
              @click="publish"
              >发布正式签表</wd-button
            ><wd-button
              v-if="
                cfg?.format === 'groups_knockout' &&
                t.draw_stage === 'initial' &&
                t.draw_published
              "
              size="small"
              :loading="busy"
              @click="draw('knockout')"
              >生成晋级淘汰签表</wd-button
            ><wd-button
              v-if="cfg?.format !== 'knockout' && t.draw_version"
              size="small"
              variant="plain"
              @click="tie"
              >确认同分排名</wd-button
            ><wd-button
              v-if="t.draw_version && t.status !== 'finished'"
              size="small"
              variant="plain"
              @click="finish"
              >结束赛事</wd-button
            ><wd-button
              v-if="t.status !== 'cancelled'"
              size="small"
              variant="plain"
              @click="cancelEvent"
              >取消赛事并退款</wd-button
            ></view
          >
          <wd-button v-if="cancelledRegistrations.length" size="small" variant="text" @click="showCancelledRecords=!showCancelledRecords">{{ showCancelledRecords ? '收起取消记录' : '查看取消记录' }}（{{ cancelledRegistrations.length }}）</wd-button>
          <view v-for="r in managementRegistrations" :key="r.id" class="list-card"
            ><view class="registration-profile"><view class="registration-identity"><ParticipantIdentity :nickname="r.user_nickname" :avatar="r.user_avatar" :level="r.user_ntrp_level" /></view><text class="muted small">{{ stateNames[r.admission || ""] }}</text></view><text class="muted"
              >{{ stateNames[r.approval || ""] }} ·
              {{ stateNames[r.payment || ""] }}</text
            ><view class="choices"
              ><wd-button
                v-if="r.payment === 'unverified'"
                size="small"
                variant="plain"
                @click="verifyLegacy(r)"
                >核验历史报名</wd-button
              ><template v-if="t.can_review && r.approval === 'pending'"
                ><wd-button size="small" @click="review(r, true)"
                  >通过</wd-button
                ><wd-button
                  size="small"
                  variant="plain"
                  @click="review(r, false)"
                  >拒绝</wd-button
                ></template
              ><wd-button
                v-if="['paid', 'verified'].includes(r.payment || '')"
                size="small"
                variant="plain"
                @click="refund(r)"
                >全额退款</wd-button
              ><wd-button
                v-if="!t.draw_version && r.admission === 'active'"
                size="small"
                variant="plain"
                @click="cancelReg(r)"
                >取消名额</wd-button
              ></view
            ></view
          >
          <view
            v-for="m in t.matches.filter((x) => x.status !== 'bye')"
            :key="m.key"
            class="list-card"
            ><text
              >#{{ m.id }} · 第 {{ m.round_no }} 轮 ·
              {{ teamName(t.teams, m.team_a_id, t.registrations) }} vs
              {{ teamName(t.teams, m.team_b_id, t.registrations) }}</text
            ><view class="choices"
              ><wd-button
                v-if="m.status === 'pending'"
                size="small"
                variant="plain"
                @click="openEdit(m, 'schedule')"
                >排场</wd-button
              ><wd-button
                v-if="t.draw_published && m.team_a_id && m.team_b_id"
                size="small"
                @click="openEdit(m, 'result')"
                >{{
                  m.status === "completed" ? "修改比分" : "录入比分"
                }}</wd-button
              ><wd-button
                v-if="m.status === 'completed'"
                size="small"
                variant="plain"
                @click="reset(m)"
                >撤销结果</wd-button
              ></view
            ></view
          >
        </view> </view
      ><view class="fixed-action"
        ><text class="price large">¥{{ t.entry_fee || 0 }}/人</text
        ><view class="registration-actions"><ActivityShare kind="tournament" :id="id" :title="t.title" :schedule="localTime(t.start_time)" :place="t.address || t.city" :people="`最多 ${t.max_participants} 人`" :fee="Number(t.entry_fee)" /><wd-button v-if="isTimelinePreview()" @click="guideToMiniProgram">进入小程序报名</wd-button><wd-button v-else
          :disabled="
            !canJoin ||
            (!t.can_register && s.loggedIn) ||
            (Number(t.entry_fee) > 0 && t.payment_method !== 'offline' && !t.prepay_enabled)
          "
          :loading="busy"
          @click="join"
          >{{
            Number(t.entry_fee) > 0 && t.payment_method !== 'offline' && !t.prepay_enabled
              ? "预付尚未开放"
              : title
          }}</wd-button
        ></view></view
      > </template
    ><view v-else class="page-loading"><wd-loading text="正在加载赛事信息" /></view>
    <wd-popup v-model="popup" position="bottom" closable
      ><view class="edit-popup">
        <text class="section-title">{{
          edit === "result"
            ? "录入比赛结果"
            : edit === "schedule"
              ? "安排场地与时间"
              : "确认同分顺序"
        }}</text>
        <template v-if="edit === 'result'"
          ><ChoiceSelect :model-value="form.winner || ''" title="胜者" :options="[selected?.team_a_id,selected?.team_b_id].filter(Boolean).map(teamId=>({value:teamId!,label:teamName(t?.teams || [],teamId,t?.registrations || [])}))" @update:model-value="form.winner=Number($event); form.is_draw=false" />
          <text class="field-label">比分（自由文本）</text
          ><wd-input v-model="form.score" placeholder="例如 6:4 6:3" /><view
            v-if="selected?.kind === 'round_robin' && cfg?.allow_draw"
            class="switch-row"
            ><text>平局</text><wd-switch v-model="form.is_draw" /></view
          ><view class="switch-row"
            ><text>弃权</text><wd-switch v-model="form.walkover" /></view
        ></template>
        <template v-else-if="edit === 'schedule'"
          ><ChoiceSelect v-model="form.court" title="场地" :options="(cfg?.courts || []).map(c=>({value:c,label:c}))" />
          <picker
            mode="date"
            :value="form.date"
            @change="form.date = $event.detail.value"
            ><view class="picker-field">{{ form.date }}</view></picker
          ><picker
            mode="time"
            :value="form.time"
            @change="form.time = $event.detail.value"
            ><view class="picker-field">{{ form.time }}</view></picker
          ></template
        >
        <template v-else
          ><text class="field-label">组号</text
          ><wd-input v-model="form.group" type="number" /><text
            class="field-label"
            >该组全部队伍 ID 的排名顺序（逗号分隔）</text
          ><wd-input v-model="form.order" placeholder="例如 21,23,22,24"
        /></template>
        <text v-if="edit !== 'schedule'" class="field-label"
          >原因（修改、撤销、同分处理必填）</text
        ><wd-input v-if="edit !== 'schedule'" v-model="form.reason" /><wd-button
          block
          :loading="busy"
          @click="submitEdit"
          >保存</wd-button
        >
      </view></wd-popup
    >
    <wd-popup
      v-model="previewOpen"
      position="bottom"
      closable
      round
      root-portal
      :safe-area-inset-bottom="true"
      custom-style="height:88vh;"
      ><scroll-view scroll-y style="height: 88vh"
        ><TournamentSchedulePreview
          v-if="schedulePreview && cfg"
          :preview="schedulePreview"
          :registrations="t?.registrations || []"
          :my-user-id="s.user?.id"
          :config="cfg" /></scroll-view
    ></wd-popup>
  </AppShell>
</template>
<style scoped>
.organizer-profile{display:flex;align-items:center;gap:10px;min-width:0}.organizer-copy{display:flex;flex-direction:column;gap:5px;min-width:0}.organizer-name{font-size:16px;line-height:24px;font-weight:600;overflow-wrap:anywhere}.organizer-type{font-size:11px;line-height:18px;color:#718579}

.fixed-action > .registration-actions{display:flex;flex-direction:row;align-items:center;gap:12px;flex:none}

.intro-pane{padding:16px!important;border:1px solid #dce8ee;border-radius:14px;background:#fff}.intro-section{display:flex;flex-direction:column;gap:10px;padding:18px 0;border-top:1px solid #e6edf1}.intro-section:first-child{padding-top:0;border-top:0}.intro-section:last-child{padding-bottom:0}.intro-heading{display:block;font-size:16px;font-weight:700;color:#244356;line-height:24px}.intro-copy{display:block;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;font-size:14px;color:#526772}.prize-row{padding:14px;background:#f0f8fd;border-left:3px solid #0787c8;border-radius:8px;display:flex;flex-direction:column;gap:8px}.prize-name{display:flex;align-items:center;gap:8px;font-size:15px;font-weight:700;line-height:22px;color:#146790}.prize-description{display:block;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.8;color:#536975}

.participant-avatars {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.tournament-content {
  padding-bottom: 120px;
}
.pane {
  padding: 16px 0;
}
.list-card {
  padding: 16px;
  background: #fff;
  border: 1px solid var(--playnow-card-border);
  border-radius: var(--playnow-card-radius);
  margin: 12px 0;
}
.choices {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}
.muted {
  display: block;
  color: #888;
  font-size: 12px;
  margin: 8px 0;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
}
.body-copy {
  display: block;
  white-space: pre-wrap;
  margin: 12px 0;
}
.gallery {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.manager {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #ddd;
}
.section-title {
  display: block;
  margin-bottom: 16px;
}
.share-button {
  font-size: 14px;
  margin: 0;
}
.edit-popup {
  padding: 28px 20px;
  max-height: 80vh;
  overflow: auto;
}
</style>

<style scoped>
.registration-profile{display:flex;align-items:center;gap:12px}.registration-profile>.registration-identity{flex:1;min-width:0}.registration-profile>.muted{flex-shrink:0}</style>
