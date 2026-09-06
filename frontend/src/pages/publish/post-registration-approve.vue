<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const id = ref(0),
  post = ref<any>(null);
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
        ><view class="row gap8"
          ><wd-img
            round
            width="42px"
            height="42px"
            :src="r.user_avatar || '/static/tennis.jpg'"
          /><view
            ><text class="strong">{{ r.user_nickname || "球友" }}</text
            ><text class="muted small">{{
              r.status === "pending" ? "等待审核" : r.status
            }}</text></view
          ></view
        ><view v-if="r.status === 'pending'" class="row gap8"
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
