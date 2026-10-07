<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import {
  onLoad,
  onShow,
  onHide,
  onUnload,
  onShareAppMessage,
} from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import TournamentBracket from "../../components/TournamentBracket.vue";
import TournamentSchedulePreview from "../../components/TournamentSchedulePreview.vue";
import {
  buildSchedulePreview,
  personalDraw,
} from "../../services/tournament-preview";
import { request } from "../../services/api";
import { payTournament } from "../../services/payment";
import { useSession } from "../../stores/session";
import {
  getTournament,
  command,
  localTime,
  teamName,
  formatNames,
  disciplineNames,
  type Tournament,
  type Match,
  type Registration,
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
const previewOpen = ref(false),
  schedulePreview = ref<ReturnType<typeof buildSchedulePreview> | null>(null);
let refreshTimer: ReturnType<typeof setInterval> | undefined;
let refreshing = false;
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
  requested_group: 0,
  gender: "" as "" | "male" | "female",
  pairing: "random" as "random" | "fixed",
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
  try {
    t.value = await getTournament(id.value);
    error.value = "";
    if (previewOpen.value) showSchedulePreview();
  } catch (e) {
    error.value = "赛事加载失败，请重试";
  }
}
onLoad(async (q) => {
  id.value = Number(q?.id);
  invite.value = String(q?.invite || "");
  await s.fetchUser().catch(() => {});
  await load();
});
function stopRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = undefined;
}
onShow(() => {
  stopRefresh();
  if (id.value) load();
  refreshTimer = setInterval(async () => {
    if (busy.value || refreshing || !id.value) return;
    refreshing = true;
    try {
      await load();
    } finally {
      refreshing = false;
    }
  }, 5000);
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

onShareAppMessage(() => ({
  title: mine.value?.invite_token
    ? `邀请你成为「${t.value?.title}」的搭档`
    : t.value?.title || "网球比赛",
  path: `/pages/common/tournament-detail?id=${id.value}${mine.value?.invite_token ? "&invite=" + mine.value.invite_token : ""}`,
}));
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
  if (cfg.value?.discipline === "mixed" && !registration.gender) {
    uni.showToast({ title: "请选择报名性别", icon: "none" });
    return;
  }
  const text =
    Number(t.value.entry_fee) > 0
      ? "取消截止前全额退款，之后由管理员处理。是否报名？"
      : "确认报名本次比赛？";
  if (!(await confirm(text))) return;
  const r = await run("register", {
    requested_group: registration.requested_group,
    gender: registration.gender || null,
    pairing: registration.pairing,
  });
  if (r?.payment === "pending") await pay();
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
  const why = await reason("取消报名（截止前全额退）");
  if (why) await run(`registrations/${r.id}/cancel`, { reason: why });
}
async function review(r: Registration, approved: boolean) {
  const why = await reason(approved ? "通过报名审核" : "拒绝报名");
  if (why) await run(`registrations/${r.id}/review`, { reason: why, approved });
}
async function pairing(fixed: boolean) {
  await run("pairing", { pairing: fixed ? "fixed" : "random" });
}
async function accept() {
  if (!s.requireLogin()) return;
  if (!mine.value) {
    uni.showToast({ title: "请先完成个人报名，再确认搭档", icon: "none" });
    return;
  }
  await run(`invitations/${invite.value}/accept`);
  invite.value = "";
  uni.showToast({ title: "搭档已确认", icon: "success" });
}
async function draw(stage = "initial") {
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
    <view v-if="error" class="content"
      ><text>{{ error }}</text
      ><wd-button @click="load">重试</wd-button></view
    >
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
        ><text class="tag">{{
          cfg
            ? formatNames[cfg.format] + " · " + disciplineNames[cfg.discipline]
            : "赛事"
        }}</text
        ><text class="muted"
          >{{ localTime(t.start_time) }} — {{ localTime(t.end_time) }}</text
        ><text class="muted"
          >{{ t.address || t.club_name }} · {{ t.current_participants }}/{{
            t.max_participants
          }}人</text
        >
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
          ><wd-tab title="介绍" name="intro"
            ><view class="pane">
              <text class="body-copy">{{
                t.description || "欢迎报名参加本次赛事"
              }}</text
              ><text v-if="t.prize" class="body-copy">奖项：{{ t.prize }}</text
              ><view class="gallery"
                ><Photo
                  v-for="img in t.images || []"
                  :key="img"
                  :src="img"
                  width="100%"
                  height="180px"
              /></view>
              <text class="muted"
                >主办方：{{ t.club_name }} {{ t.contact_name }}</text
              ><wd-button
                v-if="t.contact_phone"
                variant="plain"
                @click="uni.makePhoneCall({ phoneNumber: t.contact_phone })"
                >联系主办方</wd-button
              >
              <text class="muted"
                >报名截止：{{ localTime(t.registration_deadline) }}</text
              ><text class="muted"
                >自助取消截止：{{ localTime(t.cancellation_deadline) }}</text
              ><text class="muted"
                >截止前全额原路退款，之后由管理员处理；主办方取消全退。</text
              >
            </view></wd-tab
          >
          <wd-tab title="参与者" name="players"
            ><view class="pane">
              <template
                v-if="!cfg?.ungrouped_display && viewData?.teams?.length"
                ><view
                  v-for="team in viewData.teams"
                  :key="team.id"
                  class="list-card"
                  ><view class="participant-avatars"
                    ><Photo
                      v-for="uid in team.user_ids || []"
                      :key="uid"
                      :src="
                        t.registrations.find((r) => r.user_id === uid)
                          ?.user_avatar
                      "
                      width="32px"
                      height="32px"
                      round /></view
                  ><text>第 {{ team.group_no }} 组 · {{ name(team.id) }}</text
                  ><text class="muted"
                    >队伍 #{{ team.id }}
                    {{
                      team.origin_group
                        ? " · 原第" + team.origin_group + "组"
                        : ""
                    }}</text
                  ></view
                ></template
              >
              <template v-else
                ><view
                  v-for="r in t.registrations"
                  :key="r.id"
                  class="list-card"
                  ><Photo
                    :src="r.user_avatar"
                    width="32px"
                    height="32px"
                    round
                  /><text>{{ r.user_nickname || "选手" + r.user_id }}</text
                  ><text v-if="r.admission" class="muted"
                    >{{ stateNames[r.admission] }} ·
                    {{ stateNames[r.approval || ""] }} ·
                    {{ stateNames[r.payment || ""] }}</text
                  ></view
                ></template
              >
              <text v-if="!t.registrations.length" class="muted"
                >暂无参与者；双打每队两人，混双每队一男一女</text
              >
              <text v-if="!t.roster_frozen" class="muted"
                >待确认席位：{{
                  Math.max(
                    0,
                    (t.max_participants || 0) - t.current_participants,
                  )
                }}
                人（含待审核、待支付席位）</text
              >
            </view></wd-tab
          >
          <wd-tab title="赛程" name="bracket"
            ><view class="pane"
              ><text class="muted">{{
                t.draw_published ? "正式签表" : "待发布；管理员看到的为抽签草稿"
              }}</text
              ><view class="choices"
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
          ><view
            v-if="cfg && cfg.group_count > 1 && !t.roster_frozen && !canJoin"
            class="choices"
            ><wd-button size="small" variant="plain" @click="changeGroup(0)"
              >改为自动分组</wd-button
            ><wd-button
              v-for="g in t.registration_groups || []"
              :key="g.group_no"
              size="small"
              variant="plain"
              @click="changeGroup(g.group_no)"
              >选第 {{ g.group_no }} 组</wd-button
            ></view
          ><text>我的报名：{{ stateNames[mine.admission || ""] }}</text
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
              cfg?.discipline !== 'singles' &&
              cfg &&
              !t.roster_frozen &&
              !canJoin
            "
            ><text class="muted">{{
              mine.partner_user_id
                ? "搭档已确认：选手" + mine.partner_user_id
                : mine.pairing === "fixed"
                  ? "待确认搭档"
                  : "随机搭档，抽签时配对"
            }}</text
            ><view class="choices"
              ><wd-button size="small" variant="plain" @click="pairing(true)"
                >邀请固定搭档</wd-button
              ><wd-button size="small" variant="plain" @click="pairing(false)"
                >改为随机搭档</wd-button
              ><button
                v-if="mine.invite_token"
                open-type="share"
                class="share-button"
              >
                分享搭档邀请
              </button></view
            ></template
          >
        </view>
        <view v-if="invite" class="list-card"
          ><text>你收到一个搭档邀请。双方须各自完成报名和支付。</text
          ><wd-button block :loading="busy" @click="accept"
            >确认搭档邀请</wd-button
          ></view
        >
        <view v-if="canJoin && t.can_register" class="list-card"
          ><template v-if="cfg && cfg.group_count > 1"
            ><text>选择参赛组（抽签保持所选组别）</text
            ><view class="choices"
              ><wd-button
                size="small"
                :variant="registration.requested_group === 0 ? 'base' : 'plain'"
                @click="registration.requested_group = 0"
                >自动分组</wd-button
              ><wd-button
                v-for="g in t.registration_groups || []"
                :key="g.group_no"
                size="small"
                :variant="
                  registration.requested_group === g.group_no ? 'base' : 'plain'
                "
                @click="registration.requested_group = g.group_no"
                >第 {{ g.group_no }} 组 · {{ g.reserved }}/{{
                  g.capacity
                }}</wd-button
              ></view
            ></template
          ><template v-if="cfg?.discipline === 'mixed'"
            ><text>报名性别</text
            ><view class="choices"
              ><wd-button
                size="small"
                :variant="registration.gender === 'male' ? 'base' : 'plain'"
                @click="registration.gender = 'male'"
                >男</wd-button
              ><wd-button
                size="small"
                :variant="registration.gender === 'female' ? 'base' : 'plain'"
                @click="registration.gender = 'female'"
                >女</wd-button
              ></view
            ></template
          ><template v-if="cfg && cfg.discipline !== 'singles'"
            ><text>搭档方式</text
            ><view class="choices"
              ><wd-button
                size="small"
                :variant="registration.pairing === 'random' ? 'base' : 'plain'"
                @click="registration.pairing = 'random'"
                >随机搭档</wd-button
              ><wd-button
                size="small"
                :variant="registration.pairing === 'fixed' ? 'base' : 'plain'"
                @click="registration.pairing = 'fixed'"
                >固定搭档</wd-button
              ></view
            ></template
          ></view
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
            ><wd-button
              v-if="
                cfg &&
                t.roster_frozen &&
                t.status !== 'finished' &&
                t.status !== 'cancelled'
              "
              size="small"
              :loading="busy"
              @click="draw()"
              >{{ t.draw_version ? "重新抽签" : "生成抽签草稿" }}</wd-button
            ><wd-button
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
          <view v-for="r in t.registrations" :key="r.id" class="list-card"
            ><text
              >{{ r.user_nickname || "选手" + r.user_id }} ·
              {{ stateNames[r.admission || ""] }}</text
            ><text class="muted"
              >{{ stateNames[r.approval || ""] }} ·
              {{ stateNames[r.payment || ""] }}</text
            ><view class="choices"
              ><wd-button
                v-if="r.payment === 'unverified'"
                size="small"
                variant="plain"
                @click="verifyLegacy(r)"
                >核验历史报名</wd-button
              ><template v-if="r.approval === 'pending'"
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
        ><wd-button
          :disabled="
            !canJoin ||
            (!t.can_register && s.loggedIn) ||
            (Number(t.entry_fee) > 0 && !t.prepay_enabled)
          "
          :loading="busy"
          @click="join"
          >{{
            Number(t.entry_fee) > 0 && !t.prepay_enabled
              ? "预付尚未开放"
              : title
          }}</wd-button
        ></view
      > </template
    ><wd-loading v-else />
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
          ><text class="field-label">胜者</text
          ><view class="choices"
            ><wd-button
              v-for="teamId in [
                selected?.team_a_id,
                selected?.team_b_id,
              ].filter(Boolean)"
              :key="teamId!"
              size="small"
              :variant="form.winner === teamId ? 'base' : 'plain'"
              @click="
                form.winner = teamId!;
                form.is_draw = false;
              "
              >{{
                teamName(t?.teams || [], teamId, t?.registrations || [])
              }}</wd-button
            ></view
          ><text class="field-label">比分（自由文本）</text
          ><wd-input v-model="form.score" placeholder="例如 6:4 6:3" /><view
            v-if="selected?.kind === 'round_robin' && cfg?.allow_draw"
            class="switch-row"
            ><text>平局</text><wd-switch v-model="form.is_draw" /></view
          ><view class="switch-row"
            ><text>弃权</text><wd-switch v-model="form.walkover" /></view
        ></template>
        <template v-else-if="edit === 'schedule'"
          ><text class="field-label">场地</text
          ><view class="choices"
            ><wd-button
              v-for="c in cfg?.courts || []"
              :key="c"
              size="small"
              :variant="form.court === c ? 'base' : 'plain'"
              @click="form.court = c"
              >{{ c }}</wd-button
            ></view
          ><picker
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
  border: 1px solid #e8e8e8;
  border-radius: 12px;
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
