<script setup lang="ts">
import { ref } from "vue";
import { onShow, onHide, onUnload } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { loadPersonalRecords } from "../../services/personal-records";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
import { localTime, teamName } from "../../services/tournaments";
const s = useSession(),
  items = ref<any[]>([]),
  tours = ref<any[]>([]),
  loading = ref(false),
  tab = ref("tournaments"),
  error = ref(""),
  postError = ref("");
let timer: ReturnType<typeof setInterval> | undefined;
let refreshing = false;
let visible = false;
async function load(silent = false) {
  if (!s.requireLogin("/pages/profile/my-registrations")) {
    items.value = [];
    tours.value = [];
    return;
  }
  if (refreshing) return;
  refreshing = true;
  const userId = s.user?.id;
  if (!silent) loading.value = true;
  try {
    const records = await loadPersonalRecords();
    if (!s.loggedIn || s.user?.id !== userId || !visible) return;
    if (records.tournaments.status === "fulfilled") {
      tours.value = records.tournaments.value;
      error.value = "";
    } else error.value = "比赛记录暂时无法加载，请重试";
    if (records.posts.status === "fulfilled") {
      items.value = records.posts.value;
      postError.value = "";
    } else postError.value = "约球报名暂时无法加载，请重试";
  } finally {
    refreshing = false;
    loading.value = false;
  }
}
function stop() {
  visible = false;
  if (timer) clearInterval(timer);
  timer = undefined;
}
onShow(async () => {
  stop();
  visible = true;
  items.value = [];
  tours.value = [];
  error.value = postError.value = "";
  if (!s.requireLogin("/pages/profile/my-registrations")) return;
  try {
    await s.fetchUser();
    await load();
  } catch {
    error.value = postError.value = "无法确认登录信息，请重试";
  }
  if (visible && s.loggedIn) timer = setInterval(() => load(true), 5000);
});
onHide(stop);
onUnload(stop);
function opponent(t: any, m: any) {
  const id = t.my_draw.team_id;
  return [m.team_a_id, m.team_b_id].includes(id)
    ? teamName(
        t.teams,
        m.team_a_id === id ? m.team_b_id : m.team_a_id,
        t.registrations,
      )
    : "待晋级后确定对手";
}
</script>
<template>
  <AppShell back title="我的报名"
    ><view class="content list-content">
      <view class="text-tabs section-head"
        ><button
          :class="{ selected: tab === 'tournaments' }"
          @click="tab = 'tournaments'"
        >
          我的比赛</button
        ><button :class="{ selected: tab === 'posts' }" @click="tab = 'posts'">
          约球报名
        </button></view
      >
      <template v-if="tab === 'tournaments'">
        <view v-if="error" class="record-card"
          ><text>{{ error }}</text
          ><wd-button size="small" variant="plain" @click="load()"
            >重试</wd-button
          ></view
        >
        <view
          v-for="t in tours"
          :key="t.id"
          class="record-card"
          @click="openPage('/pages/common/tournament-detail?id=' + t.id)"
        >
          <view class="row between"
            ><text class="strong">{{ t.title }}</text
            ><text class="tag">{{
              t.provisional ? "临时预览" : "签表 v" + t.draw_version
            }}</text></view
          ><text class="muted small">{{ localTime(t.start_time) }}</text>
          <text class="muted">{{
            t.my_draw
              ? "第 " + t.my_draw.group_no + " 组 · " + t.my_draw.half
              : t.registration?.requested_group
                ? "已选第 " +
                  t.registration.requested_group +
                  " 组 · 待发布签表"
                : "自动分组 · 待发布签表"
          }}</text>
          <view
            v-for="m in t.my_draw?.matches || []"
            :key="m.key"
            class="personal-match"
            ><text>第 {{ m.round_no }} 轮 · 对手：{{ opponent(t, m) }}</text
            ><text class="muted small"
              >{{ m.status === "bye" ? "轮空晋级" : m.score || "待比赛" }} ·
              {{ localTime(m.scheduled_at) }} · {{ m.court || "待排场" }}</text
            ></view
          >
          <text v-if="!t.my_draw" class="muted small">{{
            t.registration?.admission === "cancelled"
              ? "报名已取消"
              : t.registration?.admission === "waitlisted"
                ? "候补中"
                : t.registration?.approval === "pending"
                  ? "审核中"
                  : "确认报名后由主办方发布对阵"
          }}</text> </view
        ><wd-empty
          v-if="!loading && !error && !tours.length"
          tip="还没有报名比赛"
        />
      </template>
      <template v-else>
        <view v-if="postError" class="record-card">
          <text>{{ postError }}</text>
          <wd-button size="small" variant="plain" @click="load()">重试</wd-button>
        </view>
        <view
          v-for="r in items"
          :key="r.id"
          class="record-card"
          @click="
            openPage('/pages/common/post-detail?id=' + (r.post_id || r.id))
          "
          ><view class="row between"
            ><text class="strong">{{ r.post_title || r.title }}</text
            ><text class="tag">{{
              r.status === "pending"
                ? "待审核"
                : r.status === "approved"
                  ? "已通过"
                  : r.status === "cancelled"
                    ? "已取消"
                    : r.status === "rejected"
                    ? "未通过"
                    : r.status
            }}</text></view
          ><text class="muted small"
            >{{ r.preferred_date }} {{ r.preferred_start }}</text
          ></view
        ><wd-empty v-if="!loading && !postError && !items.length" tip="还没有报名约球"
      /></template> </view
  ></AppShell>
</template>
<style scoped>
.personal-match {
  padding: 12px 0;
  border-top: 1px solid #eee;
  margin-top: 12px;
  font-size: 13px;
}
.muted {
  display: block;
  margin: 6px 0;
  color: #888;
}
</style>
