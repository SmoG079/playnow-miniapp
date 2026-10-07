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
    posts.value = await listAll("/users/me/posts");
    tours.value = [];
    if (s.isClubAdmin)
      for (const id of s.user?.managed_club_ids || [])
        tours.value.push(...(await listAll(`/tournaments?club_id=${id}`)));
  } finally {
    loading.value = false;
  }
}
onShow(() => s.fetchUser().then(load));
function close(p: any) {
  uni.showModal({
    title: "关闭活动",
    content: "关闭后不再接受报名，确定继续？",
    success: async (r) => {
      if (r.confirm) {
        await request(`/posts/${p.id}`, { method: "DELETE" });
        load();
      }
    },
  });
}
</script>
<template>
  <AppShell back title="活动管理"
    ><view class="content"
      ><view class="text-tabs section-head"
        ><button :class="{ selected: tab === 0 }" @click="tab = 0">
          约球帖</button
        ><button
          v-if="s.isClubAdmin"
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
          ><text class="strong">{{ t.title }}</text
          ><text class="muted small">{{ t.start_time }}</text></view
        ></template
      ></view
    ></AppShell
  >
</template>
