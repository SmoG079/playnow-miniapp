<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { listAll, request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession(),
  tab = ref(0),
  posts = ref<any[]>([]),
  tours = ref<any[]>([]),
  loading = ref(false);
async function load() {
  if (!s.requireLogin("/pages/profile/my-posts")) return;
  loading.value = true;
  try {
    posts.value = [];
    tours.value = [];
    const results = await Promise.allSettled([
      listAll("/users/me/posts"), listAll("/users/me/managed-tournaments"),
    ]);
    if (results[0].status === "fulfilled") posts.value = results[0].value;
    if (results[1].status === "fulfilled") tours.value = results[1].value;
    if (results.some((r) => r.status === "rejected"))
      uni.showToast({ title: "部分记录加载失败，请重试", icon: "none" });
  } catch (e: any) {
    uni.showToast({ title: e.message || "活动加载失败，请重试", icon: "none" });
  } finally {
    loading.value = false;
  }
}
onShow(async () => {
  posts.value = [];
  tours.value = [];
  if (!s.requireLogin("/pages/profile/my-posts")) return;
  try {
    await s.fetchUser();
    await load();
  } catch {
    uni.showToast({ title: "无法确认登录信息，请重试", icon: "none" });
  }
});
function close(p: any) {
  uni.showModal({
    title: "关闭活动",
    content: "关闭后不再接受报名，确定继续？",
    success: async (r) => {
      if (r.confirm) {
        try {
          await request(`/posts/${p.id}/close`, { method: "POST" });
          await load();
        } catch (e: any) {
          uni.showToast({ title: e.message || "关闭失败，请重试", icon: "none" });
        }
      }
    },
  });
}
async function closeTournament(t: any) {
  const result = await uni.showModal({ title: "关闭比赛", content: "关闭后停止报名并取消参赛资格。真实付款进入退款流程，历史付款需要人工核验。", editable: true, placeholderText: "填写关闭原因" });
  if (!result.confirm) return;
  const reason = result.content?.trim();
  if (!reason) { uni.showToast({ title: "请填写关闭原因", icon: "none" }); return; }
  try {
    await request(`/tournaments/${t.id}/cancel`, { method: "POST", data: { reason } });
    await load();
  } catch (e: any) {
    uni.showToast({ title: e.message || "关闭比赛失败，请重试", icon: "none" });
  }
}
</script>
<template>
  <AppShell back title="活动管理"
    ><view class="content"
      ><view class="text-tabs section-head"
        ><button :class="{ selected: tab === 0 }" @click="tab = 0">
          约球帖</button
        ><button
          :class="{ selected: tab === 1 }"
          @click="tab = 1"
        >
          比赛
        </button></view
      ><template v-if="tab === 0"
        ><view
          v-for="p in posts"
          :key="p.id"
          class="record-card"
          @click="openPage('/pages/common/post-detail?id=' + p.id)"
          ><view class="row between"
            ><text class="strong">{{ p.title }}</text
            ><text class="tag">{{ p.status }}</text></view
          ><text class="muted small"
            >{{ p.preferred_date }} {{ p.preferred_start }}–{{
              p.preferred_end
            }}</text
          ><view class="row gap8" @click.stop="close(p)"
            v-if="p.status !== 'closed'"
            ><wd-button size="small" variant="plain">关闭</wd-button></view
          ></view
        ><wd-empty
          v-if="!loading && !posts.length"
          tip="还没有发起活动" /></template
      ><template v-else
        ><view
          v-for="t in tours"
          :key="t.id"
          class="record-card"
          @click="openPage('/pages/common/tournament-detail?id=' + t.id)"
          ><view class="row between"><text class="strong">{{ t.title }}</text><text class="tag">{{ t.status === "cancelled" ? "已关闭" : t.status === "finished" ? "已结束" : "进行中" }}</text></view>
          <text class="muted small">{{ t.start_time }}</text>
          <view v-if="t.can_manage && !['cancelled', 'finished'].includes(t.status)" class="row gap8" @click.stop="closeTournament(t)"><wd-button size="small" variant="plain">关闭比赛</wd-button></view></view
        ><wd-empty v-if="!loading && !tours.length" tip="还没有创建或管理的比赛" /></template
      ></view
    ></AppShell
  >
</template>
