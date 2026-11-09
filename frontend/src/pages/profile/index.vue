<script setup lang="ts">
import { computed, ref } from "vue";
import { onShareAppMessage, onShow } from "@dcloudio/uni-app";
import MainHeader from "../../components/MainHeader.vue";
import AppShell from "../../components/AppShell.vue";
import { useSession } from "../../stores/session";
import { identityLabels } from "../../domain/my-activities";
import { openPage } from "../../utils/navigation";
import { enableActivitySharing, homeShare } from "../../utils/share";

// #ifdef MP-WEIXIN
onShow(() => enableActivitySharing(false));
onShareAppMessage(homeShare);
// #endif
const s = useSession();
const identities = computed(() => identityLabels(s.user));
const allowed = ref(false);
const utrAccessVerified = ref(false);
async function refreshProfile() {
  utrAccessVerified.value = false;
  try { const user = await s.fetchUser(); utrAccessVerified.value = user?.role === "platform_admin"; }
  catch { /* Keep the administrator-only entry hidden until a successful refresh. */ }
}
onShow(() => {
  allowed.value = false;
  utrAccessVerified.value = false;
  s.syncTokens();
  if (!s.loggedIn) {
    uni.redirectTo({ url: "/pages/common/login?redirect=" + encodeURIComponent("/pages/profile/index") });
    return;
  }
  allowed.value = true;
  void refreshProfile();
});
const menus = computed(() => {
  const common = [
    ["calendar-line", "我的预约", "/pages/profile/my-bookings"],
    ["history", "活动提现", "/pages/profile/activity-wallet"],
    ["user", "我的活动", "/pages/profile/my-activities"],
    ["check", "申请处理", "/pages/profile/applications"],
  ];
  if (s.isClubAdmin && s.user?.managed_club_ids?.length)
    common.splice(
      1,
      0,
      ["home", "俱乐部管理", "/pages/profile/club-dashboard"],
    );
  return common;
});
function logout() {
  uni.showModal({
    title: "退出登录",
    content: "确定要退出登录吗？",
    success: (r) => r.confirm && s.logout(),
  });
}
declare const wx: { openPrivacyContract?: (options: { fail?: () => void }) => void };
function openPrivacy() {
  // #ifdef MP-WEIXIN
  if (typeof wx !== "undefined" && typeof wx.openPrivacyContract === "function") {
    wx.openPrivacyContract({
      fail: () =>
        uni.showToast({
          title: "隐私指引暂不可用，请在小程序右上角「更多资料」查看",
          icon: "none",
        }),
    });
    return;
  }
  // #endif
  uni.showToast({
    title: "请在右上角「更多资料」查看隐私指引",
    icon: "none",
  });
}
</script>
<template>
  <AppShell v-if="allowed" active="profile"
    ><MainHeader title="我的" /><view class="content main-content"
      ><template v-if="s.loggedIn && s.user"
        ><view class="profile-header" role="button" aria-label="编辑个人资料" hover-class="profile-pressed" @click="openPage('/pages/profile/edit')"
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
          ><wd-icon name="arrow-right" size="18px" color="var(--playnow-muted)" /></view
        ><view v-if="utrAccessVerified && s.isPlatformAdmin" class="utr-entry-card" role="button" aria-label="我的 UTR 战绩" @click="openPage('/pages/profile/utr-record')"><view class="utr-entry-mark">UTR</view><view class="utr-entry-copy"><text class="utr-entry-title">我的 UTR 战绩</text><text class="utr-entry-subtitle">积分 · 等级 · 战绩 · 世界排名</text></view><wd-icon name="arrow-right" size="18px" color="var(--playnow-brand)" /></view><view class="profile-menu-list">
          <view v-for="m in menus" :key="m[2]" class="profile-menu-card">
            <wd-cell :title="m[1]" :prefix-icon="m[0]" icon-size="22px"
              title-width="calc(100% - 40px)" center is-link :border="false"
              custom-style="min-height:60px" @click="openPage(m[2])" />
          </view>
        </view>
        <view class="publish-action logout-action"
          ><wd-button block variant="plain" type="danger" @click="logout"
            >退出登录</wd-button
          ></view
        ></template
      ><view v-else-if="s.loggedIn" class="empty-state"><text class="muted">{{ s.loading ? "正在确认登录信息" : "登录信息暂不可用" }}</text><wd-button size="small" @click="refreshProfile">重试</wd-button></view
      ><view class="privacy-entry" role="button" aria-label="隐私保护指引" @click="openPrivacy"
        ><text>隐私保护指引</text></view
      ></view
    ></AppShell
  >
</template>

<style scoped>
.utr-entry-card{display:flex;align-items:center;gap:12px;padding:19px 16px;margin-bottom:14px;border:1px solid var(--playnow-card-border);border-radius:16px;background:var(--playnow-surface);}.utr-entry-mark{flex:none;color:var(--playnow-brand);font-size:25px;line-height:32px;letter-spacing:-1px;}.utr-entry-copy{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px;}.utr-entry-title{font-size:17px;line-height:24px;font-weight:600;color:var(--playnow-text);}.utr-entry-subtitle{font-size:12px;line-height:18px;color:var(--playnow-muted);}
.profile-info { flex:1; min-width:0; }
.profile-info .page-title { font-size:20px; font-weight:650; }
.identity-tags .yellow { background:#f2f3e5; color:#70744c; }
.identity-tags { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:10px; }
.identity-tags .tag { font-size:12px; line-height:16px; padding:4px 8px; border-radius:6px; }
.identity-tag { background:var(--playnow-brand-soft); color:#496756; font-weight:500; }
.profile-menu-list {
  display:flex;
  flex-direction:column;
  gap:0;
  overflow:hidden;
  border:1px solid var(--playnow-card-border);
  border-radius:var(--playnow-card-radius);
  background:var(--playnow-surface);
  --wot-cell-title-font-size:15px;
  --wot-cell-title-line-height:24px;
  --wot-cell-padding:16px;
  --wot-cell-icon-spacing-right:12px;
  --wot-cell-icon-color:#647d70;
  --wot-cell-arrow-size:16px;
  --wot-cell-arrow-color:#a0ada5;
  --wot-cell-title-color:var(--playnow-text);
}
.profile-menu-card {
  background:#fff;
  border-bottom:1px solid var(--playnow-card-border);
  overflow:hidden;
}
.profile-menu-card:last-child { border-bottom:0; }
.profile-pressed { opacity:.8; }
.logout-action { margin-top:32px; --wot-button-danger-plain-border:var(--playnow-card-border); }
.privacy-entry { display:flex; justify-content:center; margin-top:28px; }
.privacy-entry text { padding:8px 14px; font-size:12px; line-height:16px; color:var(--playnow-muted); }
</style>
