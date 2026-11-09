<script setup lang="ts">
import { ref } from "vue";
import { onShareAppMessage, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import MainHeader from "../../components/MainHeader.vue";
import { useSession } from "../../stores/session";
import { enableActivitySharing, homeShare } from "../../utils/share";

// #ifdef MP-WEIXIN
onShow(() => enableActivitySharing(false));
onShareAppMessage(homeShare);
// #endif
const s = useSession();
const allowed = ref(false);
onShow(() => {
  allowed.value = false;
  s.syncTokens();
  if (!s.loggedIn) {
    // Replace the gated page so cancelling login cannot reopen it in a loop.
    uni.redirectTo({ url: "/pages/common/login?redirect=" + encodeURIComponent("/pages/publish/index") });
    return;
  }
  allowed.value = true;
  s.fetchUser().catch(() => {});
});
function openForm(url: string) {
  if (s.requireLogin(url)) uni.navigateTo({ url });
}
function goPost() { openForm("/pages/publish/post-create"); }
function goTournament() { openForm("/pages/publish/tournament-create"); }
function goClub() { openForm("/pages/publish/club-create"); }
</script>
<template>
  <AppShell v-if="allowed" active="publish">
    <MainHeader title="发布" />
    <view class="content publish-content">
      <view class="publish-entries">
        <text class="entry-intro muted">从一场球开始。</text>
        <button class="publish-entry entry-primary" hover-class="entry-pressed" @click="goPost">
          <view class="entry-icon"><wd-icon name="user-group" size="26px" /></view>
          <view class="entry-copy">
            <view class="entry-heading"><text class="entry-title">发布约球</text></view>
            <text class="entry-description">找球友一起练球、打友谊局。</text>
          </view>
          <wd-icon name="arrow-right" size="16px" color="#a0ada5" />
        </button>
        <button class="publish-entry" hover-class="entry-pressed" @click="goTournament">
          <view class="entry-icon"><wd-icon name="trophy" size="26px" /></view>
          <view class="entry-copy">
            <view class="entry-heading"><text class="entry-title">发布比赛</text></view>
            <text class="entry-description">设置赛制，管理报名、抽签和晋级。</text>
          </view>
          <wd-icon name="arrow-right" size="16px" color="#a0ada5" />
        </button>
        <button class="publish-entry" hover-class="entry-pressed" @click="goClub">
          <view class="entry-icon"><wd-icon name="company" size="26px" /></view>
          <view class="entry-copy">
            <text class="entry-title">创建俱乐部</text>
            <text class="entry-description">建立社群，邀请常一起打球的朋友。</text>
          </view>
          <wd-icon name="arrow-right" size="16px" color="#a0ada5" />
        </button>
      </view>
    </view>
  </AppShell>
</template>
<style scoped>

.publish-entries { display:flex; flex-direction:column; gap:0; padding-bottom:24px; }
.entry-intro { display:block; margin:4px 0 24px; font-size:24px; font-weight:600; color:var(--playnow-text); line-height:1.5; }
.publish-entry { display:flex; align-items:center; gap:16px; width:100%; padding:24px 20px; border-bottom:1px solid var(--playnow-card-border); text-align:left; line-height:1.5; }
.entry-primary { margin-bottom:12px; padding:28px 20px; border:0; border-radius:var(--playnow-card-radius); background:var(--playnow-brand-deep); }
.entry-pressed { opacity:.8; }
.entry-icon { display:flex; align-items:center; justify-content:center; flex:none; width:44px; height:44px; color:var(--playnow-brand); }
.entry-copy { flex:1; min-width:0; }
.entry-heading { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.entry-title { display:block; font-size:19px; font-weight:600; color:var(--playnow-text); }
.entry-description { display:block; margin-top:8px; font-size:14px; line-height:1.7; color:var(--playnow-muted); }
.entry-primary .entry-icon, .entry-primary .entry-title { color:#fff; }
.entry-primary .entry-description { color:#d4e5da; }

</style>
