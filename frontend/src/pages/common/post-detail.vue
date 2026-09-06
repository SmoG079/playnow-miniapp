<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onPullDownRefresh } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession(),
  id = ref(""),
  post = ref<any>(null),
  comments = ref<any[]>([]),
  input = ref(""),
  reply = ref<any>(null),
  busy = ref(false),
  showRegs = ref(false);
const owner = computed(() => post.value?.user_id === s.user?.id);
const registration = computed(() =>
  post.value?.registrations?.find(
    (r: any) =>
      r.user_id === s.user?.id && ["pending", "approved"].includes(r.status),
  ),
);
const full = computed(
  () =>
    post.value && post.value.registration_count >= post.value.players_needed,
);
async function load() {
  try {
    post.value = await request(`/posts/${id.value}`);
    comments.value =
      (await request<any>(`/posts/${id.value}/comments?page=1&page_size=50`))
        .items || [];
  } catch (e: any) {
    uni.showToast({ title: e.message, icon: "none" });
  }
}
onLoad((q) => {
  id.value = String(q?.id || "");
  s.fetchUser()
    .catch(() => {})
    .finally(load);
});
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
function action() {
  if (!s.requireLogin(`/pages/common/post-detail?id=${id.value}`)) return;
  if (owner.value)
    return openPage(
      `/pages/publish/post-registration-approve?postId=${id.value}`,
    );
  if (registration.value) {
    uni.showModal({
      title: "确认取消",
      content: "确定取消报名吗？",
      success: async (r) => {
        if (r.confirm) {
          await request(`/posts/${id.value}/register`, { method: "DELETE" });
          const saved = (
            uni.getStorageSync("registered_post_ids") || []
          ).filter((x: number) => x !== Number(id.value));
          uni.setStorageSync("registered_post_ids", saved);
          load();
        }
      },
    });
    return;
  }
  if (full.value || post.value.status !== "open")
    return uni.showToast({ title: "当前活动不可报名", icon: "none" });
  if (!s.user?.phone)
    return openPage(
      `/pages/profile/edit?redirect=${encodeURIComponent("/pages/common/post-detail?id=" + id.value)}`,
    );
  uni.showModal({
    title: "确认报名",
    content: `确定报名参加「${post.value.title}」吗？`,
    success: async (r) => {
      if (r.confirm) {
        await request(`/posts/${id.value}/register`, {
          method: "POST",
          data: { message: "" },
        });
        const saved: number[] = uni.getStorageSync("registered_post_ids") || [];
        if (!saved.includes(Number(id.value)))
          uni.setStorageSync("registered_post_ids", [
            ...saved,
            Number(id.value),
          ]);
        uni.showToast({
          title: post.value.approval_required ? "等待审核" : "报名成功",
          icon: "success",
        });
        load();
      }
    },
  });
}
async function send() {
  const content = input.value.trim();
  if (!content || busy.value) return;
  if (!s.requireLogin(`/pages/common/post-detail?id=${id.value}`)) return;
  busy.value = true;
  try {
    await request(`/posts/${id.value}/comments`, {
      method: "POST",
      data: { content, parent_id: reply.value?.id || null },
    });
    input.value = "";
    reply.value = null;
    comments.value =
      (await request<any>(`/posts/${id.value}/comments?page=1&page_size=50`))
        .items || [];
  } finally {
    busy.value = false;
  }
}
function remove(c: any) {
  if (c.user_id !== s.user?.id && !owner.value) return;
  uni.showModal({
    title: "删除评论",
    content: "确定删除这条评论吗？",
    success: async (r) => {
      if (r.confirm) {
        await request(`/posts/${id.value}/comments/${c.id}`, {
          method: "DELETE",
        });
        load();
      }
    },
  });
}
</script>
<template>
  <AppShell back title="活动详情"
    ><template v-if="post"
      ><view v-if="post.images?.length" class="detail-photo"
        ><Photo
          width="100%"
          height="100%"
          :src="post.images[0]"
          fallback="/static/tennis.jpg"
          mode="aspectFill" /></view
      ><view class="content detail-content"
        ><view class="row gap8 section-head"
          ><text class="tag">{{ post.venue_id ? "订场约球" : "自由约球" }}</text
          ><text v-if="post.level_required" class="tag yellow"
            >NTRP {{ post.level_required }}</text
          ></view
        ><text class="page-title">{{ post.title }}</text
        ><view class="detail-facts"
          ><view class="fact"
            ><wd-icon name="time-line" /><view
              ><text class="strong">{{ post.preferred_date }}</text
              ><text class="muted"
                >{{ post.preferred_start }}–{{ post.preferred_end }}</text
              ></view
            ></view
          ><view
            class="fact"
            @click="
              post.venue_latitude &&
              uni.openLocation({
                latitude: Number(post.venue_latitude),
                longitude: Number(post.venue_longitude),
                name: post.club_name,
                address: post.venue_address,
              })
            "
            ><wd-icon name="location" /><view
              ><text class="strong">{{ post.club_name || "地点待协商" }}</text
              ><text class="muted">{{ post.venue_address }}</text></view
            ></view
          ></view
        ><view class="row between section-head"
          ><text class="section-title">一起上场的球友</text
          ><text class="link" @click="showRegs = true"
            >{{ post.registration_count || 0 }}/{{
              post.players_needed
            }}
            人</text
          ></view
        ><text class="body-copy">{{
          post.description || post.notes || "发起人暂未填写更多说明。"
        }}</text
        ><view class="organizer"
          ><Photo
            round
            width="40px"
            height="40px"
            :src="post.user_avatar"
            fallback="/static/tennis.jpg"
          /><view
            ><text class="strong"
              >{{ post.user_nickname || "匿名" }} · 发起人</text
            ></view
          ><wd-button
            v-if="post.user_phone"
            size="small"
            variant="plain"
            @click="uni.makePhoneCall({ phoneNumber: post.user_phone })"
            >联系</wd-button
          ></view
        ><view class="section-head"
          ><text class="section-title">评论</text></view
        ><view
          v-for="c in comments"
          :key="c.id"
          class="comment"
          @longpress="remove(c)"
          @click="reply = { id: c.id, nickname: c.user_nickname }"
          ><text class="strong">{{ c.user_nickname || "球友" }}</text
          ><text v-if="c.reply_to_nickname" class="muted small">
            回复 {{ c.reply_to_nickname }}</text
          ><text class="body-copy">{{ c.content }}</text></view
        ><text v-if="reply" class="muted small"
          >回复 {{ reply.nickname }}
          <text class="link" @click.stop="reply = null">取消</text></text
        ><view class="comment-input"
          ><wd-input
            v-model="input"
            :placeholder="reply ? '回复 ' + reply.nickname : '说点什么…'"
          /><wd-button size="small" :loading="busy" @click="send"
            >发送</wd-button
          ></view
        ></view
      ><view class="fixed-action"
        ><view
          ><text class="price large">¥{{ post.price || 0 }}</text
          ><text class="small muted">/ 人</text></view
        ><wd-button
          :disabled="!owner && (full || post.status !== 'open')"
          @click="action"
          >{{
            owner
              ? "管理报名"
              : registration
                ? registration.status === "pending"
                  ? "待审核 · 取消"
                  : "已报名 · 取消"
                : full
                  ? "已满员"
                  : "报名参加"
          }}</wd-button
        ></view
      ><wd-popup v-model="showRegs" position="bottom"
        ><view class="sheet"
          ><text class="section-title">报名成员</text
          ><wd-cell
            v-for="r in post.registrations"
            :key="r.user_id"
            :title="r.user_nickname || '球友'"
            :value="r.status === 'pending' ? '待审核' : '已通过'" /><wd-empty
            v-if="!post.registrations?.length"
            tip="还没有人报名" /></view></wd-popup></template
    ><wd-loading v-else
  /></AppShell>
</template>
