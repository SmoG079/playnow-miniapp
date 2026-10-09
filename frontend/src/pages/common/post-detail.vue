<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onPullDownRefresh } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
import { postLocation } from "../../domain/post-location";
const s = useSession(),
  id = ref(""),
  post = ref<any>(null),
  postFailed = ref(false),
  postLoading = ref(true),
  commentsFailed = ref(false),
  comments = ref<any[]>([]),
  input = ref(""),
  reply = ref<any>(null),
  busy = ref(false),
  showRegs = ref(false);
const location = computed(() => postLocation(post.value || {}));
function openMeetingLocation() {
  const point = location.value;
  if (point.latitude == null || point.longitude == null) return;
  uni.openLocation({ latitude:Number(point.latitude), longitude:Number(point.longitude), name:point.title, address:point.address });
}
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
  if (postLoading.value && post.value) return;
  postLoading.value = true;
  postFailed.value = false;
  try {
    post.value = await request(`/posts/${id.value}`);
    await loadComments();
  } catch (e: any) {
    postFailed.value = true;
  } finally {
    postLoading.value = false;
  }
}
async function loadComments() {
  commentsFailed.value = false;
  try {
    comments.value = (await request<any>(`/posts/${id.value}/comments?page=1&page_size=50`)).items || [];
  } catch {
    commentsFailed.value = true;
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
        ><view v-if="postFailed" class="row between section-head">
          <text class="muted small">刷新失败，当前显示上次加载的内容</text>
          <wd-button size="small" variant="text" @click="load">重试</wd-button>
        </view><view class="row gap8 section-head"
          ><text class="tag">{{ post.venue_id ? "订场约球" : "自由约球" }}</text
          ><text v-if="post.level_required" class="tag yellow"
            >NTRP {{ post.level_required }}</text
          ></view
        ><text class="page-title">{{ post.title }}</text
        ><view class="detail-facts"
          ><view class="fact"
            ><view class="fact-icon"><wd-icon name="time-line" size="18px" /></view><view
              ><text class="strong">{{ post.preferred_date }}</text
              ><text class="muted"
                >{{ post.preferred_start }}–{{ post.preferred_end }}</text
              ></view
            ></view
          ><view class="fact" @click="openMeetingLocation"><view class="fact-icon"><wd-icon name="location" size="18px" /></view><view><text class="strong">{{ location.title }}</text><text v-if="location.address && location.address !== location.title" class="muted">{{ location.address }}</text><text v-if="location.latitude != null && location.longitude != null" class="muted">点击查看地图与导航</text></view></view
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
        ><view v-if="commentsFailed" class="row between">
          <text class="muted small">评论加载失败</text>
          <wd-button size="small" variant="text" @click="loadComments">重试</wd-button>
        </view><view
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
          :disabled="!owner && !registration && (full || post.status !== 'open')"
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
            :value="r.status === 'pending' ? '待审核' : r.status === 'approved' ? '已通过' : r.status === 'cancelled' ? '已取消' : '未通过'" /><wd-empty
            v-if="!post.registrations?.length"
            tip="还没有人报名" /></view></wd-popup></template
    ><view v-else-if="postFailed" class="content empty-state">
      <wd-icon name="info-circle" size="44px" color="#728178" />
      <text class="section-title">活动信息加载失败</text>
      <text class="muted">请检查网络后重新加载</text>
      <wd-button size="small" @click="load">重新加载</wd-button>
    </view>
    <view v-else class="page-loading"><wd-loading text="正在加载活动信息" /></view>
  </AppShell>
</template>

<style scoped>
.detail-facts .fact > .fact-icon { flex:0 0 22px; width:22px; align-items:center; }
</style>
