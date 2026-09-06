<script setup lang="ts">
import { computed, ref } from "vue";
import { onPullDownRefresh, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { openPage } from "../../utils/navigation";
const tab = ref(0),
  mode = ref("all"),
  date = ref(""),
  ntrp = ref(""),
  distance = ref(false),
  posts = ref<any[]>([]),
  tournaments = ref<any[]>([]),
  loading = ref(false);
const levels = [
  "不限",
  "1.0",
  "1.5",
  "2.0",
  "2.5",
  "3.0",
  "3.5",
  "4.0",
  "4.5",
  "5.0",
  "5.5",
  "6.0",
  "6.5",
  "7.0",
];
const visiblePosts = computed(() =>
  posts.value.filter(
    (p) =>
      (mode.value === "all" ||
        (mode.value === "free" ? !p.venue_id : !!p.venue_id)) &&
      (!date.value || p.preferred_date === date.value),
  ),
);
async function load() {
  loading.value = true;
  try {
    let extra = ntrp.value ? `&ntrp_levels=${ntrp.value}` : "";
    if (distance.value) {
      try {
        const loc: any = await uni.getLocation({ type: "gcj02" });
        extra += `&sort_by=distance&lat=${loc.latitude}&lng=${loc.longitude}`;
      } catch {
        distance.value = false;
      }
    }
    const [p, t] = await Promise.all([
      request<PageResult<any>>(`/posts?page=1&page_size=20${extra}`),
      request<PageResult<any>>(
        `/tournaments?status=open&page=1&page_size=10${distance.value ? extra.replace(/&ntrp_levels=[^&]+/, "") : ""}`,
      ),
    ]);
    posts.value = p.items || [];
    tournaments.value = t.items || [];
  } catch (e: any) {
    uni.showToast({ title: e.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
onShow(() => {
  load();
});
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
function dateChange(e: any) {
  date.value = e.detail.value;
}
</script>
<template>
  <AppShell active="home"
    ><view class="home-header"
      ><text class="brand">PlayNow<text class="brand-dot">.</text></text
      ><text class="page-title">今天，球场见。</text></view
    ><view class="content"
      ><view class="text-tabs section-head"
        ><button :class="{ selected: tab === 0 }" @click="tab = 0">
          约球广场</button
        ><button :class="{ selected: tab === 1 }" @click="tab = 1">
          比赛
        </button></view
      ><template v-if="tab === 0"
        ><view class="filter-row"
          ><wd-button
            v-for="x in [
              ['all', '全部'],
              ['free', '自由'],
              ['venue', '订场'],
            ]"
            :key="x[0]"
            size="small"
            :type="mode === x[0] ? 'primary' : 'info'"
            variant="plain"
            @click="mode = x[0]"
            >{{ x[1] }}</wd-button
          ><picker mode="date" :value="date" @change="dateChange"
            ><wd-button size="small" variant="plain">{{
              date || "日期"
            }}</wd-button></picker
          ><wd-button
            size="small"
            variant="plain"
            @click="
              distance = !distance;
              load();
            "
            >{{ distance ? "距离排序" : "按距离" }}</wd-button
          ></view
        ><scroll-view scroll-x class="chip-scroll"
          ><view class="choices nowrap"
            ><button
              v-for="l in levels"
              :key="l"
              :class="{ chosen: ntrp === (l === '不限' ? '' : l) }"
              @click="
                ntrp = l === '不限' ? '' : l;
                load();
              "
            >
              {{ l }}
            </button></view
          ></scroll-view
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
  ></AppShell>
</template>
