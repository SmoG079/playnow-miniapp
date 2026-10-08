<script setup lang="ts">
import { computed } from "vue";
import { onShow } from "@dcloudio/uni-app";
import MainHeader from "../../components/MainHeader.vue";
import AppShell from "../../components/AppShell.vue";
import { useSession } from "../../stores/session";
import { identityLabels } from "../../domain/my-activities";
import { openPage } from "../../utils/navigation";
const s = useSession();
const identities = computed(() => identityLabels(s.user));
onShow(() => s.fetchUser().catch(() => {}));
const menus = computed(() => {
  const common = [
    ["calendar-line", "我的预约", "/pages/profile/my-bookings"],
    ["user", "我的活动", "/pages/profile/my-activities"],
    ["check", "申请处理", "/pages/profile/applications"],
    ["notification", "系统通知", "/pages/chat/conversation?peer=system"],
  ];
  if (s.isClubAdmin && s.user?.managed_club_ids?.length)
    common.splice(
      1,
      0,
      ["home", "俱乐部管理", "/pages/profile/club-dashboard"],
    );
  if (s.isPlatformAdmin)
    common.push(["money-circle", "分账记录", "/pages/profile/settlement-list"]);
  return common;
});
function logout() {
  uni.showModal({
    title: "退出登录",
    content: "确定要退出登录吗？",
    success: (r) => r.confirm && s.logout(),
  });
}
</script>
<template>
  <AppShell active="profile"
    ><MainHeader title="我的" /><view class="content main-content"
      ><template v-if="s.loggedIn && s.user"
        ><view class="profile-header" @click="openPage('/pages/profile/edit')"
          ><Photo
            round
            width="64px"
            height="64px"
            :src="s.user?.avatar_url"
            fallback="/static/tennis.jpg"
          /><view class="profile-info"
            ><text class="page-title compact">{{
              s.user?.nickname || "网球爱好者"
            }}</text
            ><view class="identity-tags">
              <text v-for="identity in identities" :key="identity" class="tag identity-tag">{{ identity }}</text>
              <text v-if="s.user?.ntrp_level" class="tag yellow">NTRP {{ s.user.ntrp_level }}</text>
            </view></view
          ></view
        ><view class="profile-menu-list">
          <view v-for="m in menus" :key="m[2]" class="profile-menu-card">
            <wd-cell :title="m[1]" :prefix-icon="m[0]" icon-size="22px"
              title-width="calc(100% - 40px)" center is-link :border="false"
              custom-style="min-height:60px" @click="openPage(m[2])" />
          </view>
        </view>
        <view class="publish-action"
          ><wd-button block variant="plain" type="danger" @click="logout"
            >退出登录</wd-button
          ></view
        ></template
      ><view v-else-if="s.loggedIn" class="empty-state"><text class="muted">{{ s.loading ? "正在确认登录信息" : "登录信息暂不可用" }}</text><wd-button size="small" @click="s.fetchUser().catch(() => {})">重试</wd-button></view
      ><view v-else class="empty-state"
        ><wd-icon name="user" size="52px" color="#147553" /><text
          class="section-title"
          >登录后开启完整体验</text
        ><text class="muted">报名、订场、发布活动与管理俱乐部</text
        ><wd-button @click="openPage('/pages/common/login')"
          >微信登录</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>

<style scoped>
.profile-info { flex:1; min-width:0; }
.profile-info .page-title { font-size:20px; font-weight:650; }
.identity-tags .yellow { background:#f2f3e5; color:#70744c; }
.identity-tags { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:10px; }
.identity-tags .tag { font-size:12px; line-height:16px; padding:4px 8px; border-radius:6px; }
.identity-tag { background:#edf3ef; color:#496756; font-weight:500; }
.profile-menu-list {
  display:flex;
  flex-direction:column;
  gap:10px;
  --wot-cell-title-font-size:17px;
  --wot-cell-title-line-height:24px;
  --wot-cell-padding:18px;
  --wot-cell-icon-spacing-right:12px;
  --wot-cell-icon-color:#647d70;
  --wot-cell-arrow-size:16px;
  --wot-cell-arrow-color:#a0ada5;
  --wot-cell-title-color:#304238;
}
.profile-menu-card {
  background:#fff;
  border:1px solid var(--playnow-card-border);
  border-radius:var(--playnow-card-radius);
  overflow:hidden;
}
</style>
