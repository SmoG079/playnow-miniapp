<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import MainHeader from "../../components/MainHeader.vue";
import { useSession } from "../../stores/session";
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
        <text class="entry-intro muted">约上球友，或组织一场属于你的比赛。</text>
        <button class="publish-entry" hover-class="entry-pressed" @click="goPost">
          <view class="entry-icon"><wd-icon name="user-group" size="26px" /></view>
          <view class="entry-copy">
            <view class="entry-heading"><text class="entry-title">发布约球</text><wd-tag type="primary" variant="light" size="small">日常约球</wd-tag></view>
            <text class="entry-description">找球友一起练球、打友谊局。</text>
          </view>
          <wd-icon name="arrow-right" size="16px" color="#a0ada5" />
        </button>
        <button class="publish-entry" hover-class="entry-pressed" @click="goTournament">
          <view class="entry-icon"><wd-icon name="trophy" size="26px" /></view>
          <view class="entry-copy">
            <view class="entry-heading"><text class="entry-title">发布比赛</text><wd-tag type="primary" variant="light" size="small">正式比赛</wd-tag></view>
            <text class="entry-description">设置赛制，管理报名、抽签和晋级。</text>
          </view>
          <wd-icon name="arrow-right" size="16px" color="#a0ada5" />
        </button>
        <button class="publish-entry" hover-class="entry-pressed" @click="goClub">
          <view class="entry-icon"><wd-icon name="company" size="26px" /></view>
          <view class="entry-copy">
            <text class="entry-title">创建俱乐部</text>
            <text class="entry-description">让球友相聚，管理你的俱乐部和球场。</text>
          </view>
          <wd-icon name="arrow-right" size="16px" color="#a0ada5" />
        </button>
      </view>
    </view>
  </AppShell>
</template>
<style scoped>
.publish-entries { display:flex; flex-direction:column; gap:14px; padding-bottom:24px; }
.entry-intro { display:block; margin:0 0 6px; font-size:13px; line-height:1.7; }
.publish-entry {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 22px 16px;
  border: 1px solid var(--playnow-card-border);
  border-radius: var(--playnow-card-radius);
  background: #fff;
  text-align: left;
  line-height: 1.5;
}
.entry-pressed { background: #edf5ef; }
.entry-icon { display: flex; align-items: center; justify-content: center; flex: none; width: 48px; height: 48px; border-radius: 14px; background: #e8f1ec; color: #147553; }
.entry-copy { flex: 1; min-width: 0; }
.entry-heading { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.entry-title { display: block; font-size: 18px; font-weight: 650; color: #20362c; }
.entry-description { display: block; margin-top: 8px; font-size: 13px; line-height: 1.7; color: #728178; }
</style>
