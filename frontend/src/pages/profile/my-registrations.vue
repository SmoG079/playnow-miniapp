<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession(),
  items = ref<any[]>([]),
  loading = ref(false);
onShow(async () => {
  if (!s.requireLogin("/pages/profile/my-registrations")) return;
  loading.value = true;
  try {
    const ids: number[] = uni.getStorageSync("registered_post_ids") || [];
    const posts = await Promise.all(
      ids.map((id) => request<any>(`/posts/${id}`).catch(() => null)),
    );
    items.value = posts.filter(Boolean).map((post) => {
      const registration =
        (post.registrations || []).find((r: any) => r.user_id === s.user?.id) ||
        {};
      return {
        ...registration,
        post_id: post.id,
        post_title: post.title,
        preferred_date: post.preferred_date,
        preferred_start: post.preferred_start,
      };
    });
  } finally {
    loading.value = false;
  }
});
</script>
<template>
  <AppShell back title="我的报名"
    ><view class="content list-content"
      ><view
        v-for="r in items"
        :key="r.id"
        class="record-card"
        @click="openPage('/pages/common/post-detail?id=' + (r.post_id || r.id))"
        ><view class="row between"
          ><text class="strong">{{ r.post_title || r.title }}</text
          ><text class="tag">{{
            r.status === "pending"
              ? "待审核"
              : r.status === "approved"
                ? "已通过"
                : r.status
          }}</text></view
        ><text class="muted small"
          >{{ r.preferred_date }} {{ r.preferred_start }}</text
        ></view
      ><wd-empty v-if="!loading && !items.length" tip="还没有报名活动" /></view
  ></AppShell>
</template>
