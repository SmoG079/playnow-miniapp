<script setup lang="ts">
import ParticipantIdentity from "../../components/ParticipantIdentity.vue";
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const id = ref(0),
  post = ref<any>(null);
const statusLabels: Record<string, string> = {
  pending: "等待审核", approved: "已通过", rejected: "未通过", cancelled: "已取消",
};
async function load() {
  post.value = await request(`/posts/${id.value}`);
}
onLoad((q) => {
  id.value = Number(q?.postId);
  load();
});
async function review(r: any, status: string) {
  await request(`/posts/${id.value}/registrations/${r.user_id}`, {
    method: "PUT",
    data: { status },
  });
  uni.showToast({ title: "已处理", icon: "success" });
  load();
}
</script>
<template>
  <AppShell back title="报名审核"
    ><view class="content list-content"
      ><text v-if="post" class="page-title compact">{{ post.title }}</text
      ><view
        v-for="r in post?.registrations || []"
        :key="r.user_id"
        class="record-card"
        ><view class="registration-person"
          ><view class="registration-identity"><ParticipantIdentity :nickname="r.user_nickname" :avatar="r.user_avatar" :level="r.user_ntrp_level" /></view>
          <text class="registration-status" :class="'status-' + r.status">{{ statusLabels[r.status] }}</text
          ></view
        ><view v-if="r.status === 'pending'" class="registration-actions"
          ><wd-button size="small" @click="review(r, 'approved')"
            >通过</wd-button
          ><wd-button
            size="small"
            variant="plain"
            type="danger"
            @click="review(r, 'rejected')"
            >拒绝</wd-button
          ></view
        ></view
      ><wd-empty
        v-if="post && !post.registrations?.length"
        tip="暂无报名" /></view
  ></AppShell>
</template>

<style scoped>
.registration-person{display:flex;align-items:center;justify-content:flex-start;gap:10px;text-align:left}
.registration-identity{flex:1;min-width:0}
.registration-name{flex:1;min-width:0;line-height:1.5;overflow-wrap:anywhere}
.registration-status{flex-shrink:0;font-size:12px;color:#839087}
.status-approved{color:#159660}
.status-pending{color:#b27b21}
.registration-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}
</style>
