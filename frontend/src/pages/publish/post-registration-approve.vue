<script setup lang="ts">
import ParticipantIdentity from "../../components/ParticipantIdentity.vue";
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const id = ref(0),
  post = ref<any>(null),
  refunding = ref("");
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
  try {
    await request(`/posts/${id.value}/registrations/${r.user_id}`, {
      method: "PUT",
      data: { status },
    });
  } catch (e: any) {
    // A refused refund keeps the signup reviewable; the host fixes the balance and retries.
    if (e?.statusCode === 502) {
      const detail = String(e?.message || "").replace(/^退款失败：/, "").trim();
      uni.showModal({
        title: "退款失败",
        content: `${detail || "微信未受理退款"}。请到微信商户平台核对后重试。`,
        showCancel: false,
      });
    } else {
      uni.showToast({ title: e?.message || "操作失败", icon: "none" });
    }
    load();
    return;
  }
  uni.showToast({ title: "已处理", icon: "success" });
  load();
}
function confirmRefund(r: any) {
  return new Promise<boolean>((resolve) =>
    uni.showModal({
      title: "全额退款",
      content: `确定取消 ${r.user_nickname || "该选手"} 的报名并全额退款吗？`,
      success: (res) => resolve(!!res.confirm),
      fail: () => resolve(false),
    }),
  );
}
async function refund(r: any) {
  if (refunding.value || !(await confirmRefund(r))) return;
  refunding.value = r.user_id;
  try {
    await request(`/posts/${id.value}/registrations/${r.user_id}/refund`, {
      method: "POST",
    });
    uni.showToast({ title: "已退款", icon: "success" });
  } catch (e: any) {
    // A refused refund keeps the signup so the same button can retry after a top-up.
    if (e?.statusCode === 502) {
      const detail = String(e?.message || "").replace(/^退款失败：/, "").trim();
      uni.showModal({
        title: "退款失败",
        content: `${detail || "微信未受理退款"}。请到微信商户平台核对后重试。`,
        showCancel: false,
      });
    } else {
      uni.showToast({ title: e?.message || "退款失败", icon: "none" });
    }
  } finally {
    refunding.value = "";
    load();
  }
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
          <text class="registration-status" :class="'status-' + r.status">{{ r.payment === 'pending' ? '待线上付款' : statusLabels[r.status] }}</text
          ></view
        ><view v-if="r.status === 'pending' && r.payment !== 'pending'" class="registration-actions"
          ><wd-button size="small" @click="review(r, 'approved')"
            >通过</wd-button
          ><wd-button
            size="small"
            variant="plain"
            type="danger"
            @click="review(r, 'rejected')"
            >拒绝</wd-button
          ></view
        ><view
          v-if="r.payment === 'paid' && r.status === 'approved'"
          class="registration-actions"
          ><wd-button
            size="small"
            variant="plain"
            :loading="refunding === r.user_id"
            @click="refund(r)"
            >全额退款</wd-button
          ></view
        ><view
          v-else-if="r.payment === 'paid' && r.status === 'cancelled'"
          class="registration-actions"
          ><wd-button size="small" variant="plain" disabled>已退款</wd-button></view
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
.registration-status{flex-shrink:0;font-size:12px;color:var(--playnow-muted)}
.status-approved{color:var(--playnow-brand)}
.status-pending{color:#b27b21}
.registration-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}
</style>
