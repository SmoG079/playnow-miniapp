<script setup lang="ts">
import { computed, ref } from "vue";
import { onShow, onHide, onUnload, onPullDownRefresh } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import MainHeader from "../../components/MainHeader.vue";
import Photo from "../../components/Photo.vue";
import { useSession } from "../../stores/session";
import { getMyUtrRecord, utrValue, utrRank, UTR_SOURCE_NOTE, type UtrRecord } from "../../services/utr-record";
const session = useSession();
const record = ref<UtrRecord | null>(null);
const loading = ref(true), denied = ref(false), error = ref("");
const stats = computed(() => record.value);
const unsynced = computed(() => stats.value && [stats.value.rating, stats.value.matches_played, stats.value.wins, stats.value.losses, stats.value.world_rank].every(value => value === null));
let version = 0;
function stop() { version++; record.value = null; }
async function load() {
  const current = ++version;
  record.value = null; loading.value = true; denied.value = false; error.value = "";
  if (!session.requireLogin("/pages/profile/utr-record")) { loading.value = false; return; }
  try {
    const user = await session.fetchUser();
    if (current !== version) return;
    if (!user) { error.value = "无法确认登录信息，请重新加载"; return; }
    if (user.role !== "platform_admin") { denied.value = true; return; }
    const result = await getMyUtrRecord();
    if (current === version && session.loggedIn && session.user?.id === user.id && session.isPlatformAdmin) record.value = result;
  } catch (cause: any) {
    if (current !== version) return;
    if (cause.statusCode === 403) denied.value = true;
    else error.value = cause.message || "战绩暂时无法加载，请稍后重试";
  } finally { if (current === version) loading.value = false; }
}
onShow(load); onHide(stop); onUnload(stop);
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
</script>
<template>
  <AppShell><view class="utr-page"><MainHeader back title="我的 UTR 战绩" :context="false" />
    <view v-if="loading" class="utr-feedback"><wd-loading color="#19b9ce" /><text>正在加载战绩…</text></view>
    <view v-else-if="denied" class="utr-feedback"><wd-icon name="lock" size="38px" color="#71838e" /><text>仅系统管理员可查看</text></view>
    <view v-else-if="error" class="utr-feedback"><text>{{ error }}</text><wd-button size="small" @click="load">重新加载</wd-button></view>
    <template v-else-if="record">
      <view class="utr-hero">
        <view class="utr-player"><view class="utr-avatar"><Photo v-if="record.avatar_url" :src="record.avatar_url" width="40px" height="40px" round /><text v-else>{{ (record.nickname || '球友').slice(0, 1) }}</text></view><view><text class="utr-player-name">{{ record.nickname || '网球爱好者' }}</text><text class="utr-player-sport">网球 · TENNIS</text></view></view>
        <view class="utr-rating-heading"><view class="utr-brand">UTR <text class="utr-brand-caption">RATING</text></view></view>
        <view class="utr-rating-row"><view class="utr-primary-rating"><text class="utr-rating-number">{{ utrValue(stats?.rating, 2) }}</text><text class="utr-rating-label">UTR 积分</text></view><view class="utr-ntrp"><text class="utr-ntrp-label">NTRP 等级</text><text class="utr-ntrp-value">{{ utrValue(record.ntrp_level, 1) }}</text><text class="utr-ntrp-caption">网球等级</text></view></view>
        <view class="utr-hero-footer"><text class="utr-source-brand">· UTR SPORTS</text><text>我的球员档案</text></view>
      </view>
      <view class="utr-body">
        <text v-if="unsynced" class="utr-unsynced">暂无已同步的 UTR 战绩</text>
        <view class="utr-heading"><text class="utr-section-title">比赛数据</text><text class="utr-section-caption">累计战绩</text></view>
        <view class="utr-stat-card"><view class="utr-total"><view><text class="utr-overline">MATCHES PLAYED</text><text class="utr-total-label">比赛总场次</text></view><view class="utr-count"><text class="utr-count-value">{{ utrValue(stats?.matches_played) }}</text><text class="utr-unit">场</text></view></view><view class="utr-winloss"><view class="utr-result"><view><text class="utr-result-label">获胜</text><text class="utr-result-en">WINS</text></view><view class="utr-count"><text class="utr-result-value">{{ utrValue(stats?.wins) }}</text><text class="utr-unit">场</text></view></view><view class="utr-result"><view><text class="utr-result-label utr-result-loss">失利</text><text class="utr-result-en">LOSSES</text></view><view class="utr-count"><text class="utr-result-value">{{ utrValue(stats?.losses) }}</text><text class="utr-unit">场</text></view></view></view></view>
        <view class="utr-heading utr-ranking-heading"><text class="utr-section-title">世界排名</text><text class="utr-section-caption">{{ stats?.age_group ? '年龄组 · '+stats.age_group : '年龄组待同步' }}</text></view>
        <view class="utr-ranking-card"><view class="utr-rank-symbol"><wd-icon name="trophy" size="23px" color="#1499ad" /><text class="utr-rank-en">WORLD RANKING</text></view><view class="utr-rank-copy"><view class="utr-rank-number"><text v-if="stats?.world_rank !== null && stats?.world_rank !== undefined" class="utr-hash">#</text><text>{{ utrRank(stats?.world_rank) }}</text></view><text class="utr-rank-caption">所在年龄段世界排名</text></view></view>
        <view class="utr-note"><view class="utr-note-heading"><wd-icon name="info-circle" size="13px" /><text>数据说明</text></view><text class="utr-note-copy">{{ UTR_SOURCE_NOTE }}</text></view>
        <view class="utr-page-footer"><text class="utr-footer-brand">PLAYNOW</text><text>每一次上场，都有记录。</text></view>
      </view>
    </template>
  </view></AppShell>
</template>
<style scoped>
.utr-page{min-height:100vh;background:#f1f4f7;color:#10212b;--wot-color-theme:#1195a8;--wot-primary-6:#1195a8;--wot-button-primary-bg-color:#1195a8;--wot-button-primary-border-color:#1195a8;}
.utr-page :deep(.main-header){margin-bottom:0;background:#080d11;border-bottom:0;}.utr-page :deep(.main-header .page-title),.utr-page :deep(.header-back){color:#fff;}
.utr-page :deep(.header-back){background:transparent;border:0;}
.utr-hero{padding:12px 20px 16px;background:#080d11;color:#fff;}.utr-player{display:flex;align-items:center;gap:10px;margin:0 0 23px;}.utr-avatar{display:flex;align-items:center;justify-content:center;flex:none;width:40px;height:40px;border:1px solid #316370;border-radius:50%;overflow:hidden;background:#173e46;color:#56dfef;font-size:17px;font-weight:600;}.utr-player-name{display:block;font-size:16px;font-weight:600;line-height:22px;}.utr-player-sport{display:block;font-size:10px;line-height:16px;letter-spacing:1px;color:#92a5b0;margin-top:3px;}
.utr-rating-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;}.utr-brand{font-size:24px;color:#56dfef;line-height:28px;letter-spacing:.5px;}.utr-brand-caption{font-size:11px;letter-spacing:2px;color:#a2b6c0;margin-left:6px;}
.utr-rating-row{display:flex;align-items:center;gap:15px;margin:13px 0 22px;}.utr-primary-rating{flex:1;min-width:0;}.utr-rating-number{display:block;font-family:'DIN Condensed','Arial Narrow',sans-serif;font-size:88px;font-weight:400;line-height:1.1;letter-spacing:-3px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}.utr-rating-label{display:block;font-size:11px;line-height:18px;color:#a9bec9;margin-top:3px;}.utr-ntrp{width:112px;flex:none;border-left:1px solid #384851;padding-left:20px;}.utr-ntrp-label{display:block;font-size:11px;color:#a9bec9;line-height:18px;}.utr-ntrp-value{display:block;font-size:41px;line-height:1.25;letter-spacing:-1.5px;color:#56dfef;margin-top:5px;font-variant-numeric:tabular-nums;}.utr-ntrp-caption{display:block;font-size:10px;line-height:16px;color:#8ba1ad;margin-top:4px;}.utr-hero-footer{display:flex;justify-content:space-between;gap:10px;border-top:1px solid #26363f;padding-top:12px;color:#819ba9;font-size:10px;line-height:16px;}.utr-source-brand{color:#9ab8c5;font-size:9px;letter-spacing:1.6px;}
.utr-body{padding:22px 16px 24px;}.utr-unsynced{display:block;padding:10px 12px;margin-bottom:18px;border:1px solid #dce5eb;border-radius:10px;background:#fff;color:#73838e;font-size:12px;line-height:20px;}.utr-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:12px;}.utr-section-title{font-size:17px;font-weight:650;line-height:24px;}.utr-section-caption{font-size:11px;color:#73838e;line-height:18px;}.utr-stat-card{overflow:hidden;border:1px solid #dce5eb;border-radius:18px;background:#fff;}.utr-total{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:18px;}.utr-overline{display:block;font-size:9px;line-height:14px;letter-spacing:1.8px;color:#73838e;margin-bottom:5px;}.utr-total-label{font-size:14px;line-height:20px;}.utr-count{display:flex;align-items:baseline;gap:4px;min-width:0;}.utr-count-value{font-size:37px;font-weight:600;line-height:41px;letter-spacing:-1px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}.utr-unit{font-size:11px;line-height:18px;color:#73838e;}.utr-winloss{display:flex;padding:15px 0;background:#fbfdfe;border-top:1px solid #dce5eb;}.utr-result{flex:1;min-width:0;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 18px;}.utr-result+.utr-result{border-left:1px solid #dce5eb;}.utr-result-label{display:block;font-size:12px;line-height:18px;}.utr-result-label::before{content:'';display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:5px;background:#13a9bf;vertical-align:middle;}.utr-result-loss::before{background:#c96667;}.utr-result-en{display:block;margin-left:10px;font-size:9px;line-height:14px;letter-spacing:1.2px;color:#73838e;}.utr-result-value{font-size:28px;font-weight:600;line-height:34px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}
.utr-ranking-heading{margin-top:24px;}.utr-ranking-card{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:19px 18px;border:1px solid #dce5eb;border-radius:18px;background:#fff;}.utr-rank-symbol{display:flex;flex-direction:column;align-items:flex-start;gap:7px;flex:none;}.utr-rank-en{font-size:8px;line-height:14px;letter-spacing:1px;color:#73838e;}.utr-rank-copy{min-width:0;text-align:right;}.utr-rank-number{font-size:35px;font-weight:600;line-height:44px;letter-spacing:-1.5px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}.utr-hash{font-size:20px;color:#1db7c9;margin-right:3px;}.utr-rank-caption{display:block;font-size:10px;line-height:16px;color:#73838e;margin-top:5px;}.utr-note{padding:13px 3px 0;color:#73838e;}.utr-note-heading{display:flex;align-items:center;gap:5px;font-size:11px;line-height:18px;}.utr-note-copy{display:block;margin-top:5px;font-size:11px;line-height:1.85;overflow-wrap:anywhere;}.utr-page-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid #dce5eb;margin-top:22px;padding-top:13px;color:#73838e;font-size:10px;line-height:18px;}.utr-footer-brand{font-weight:600;letter-spacing:2px;color:#10212b;}.utr-feedback{display:flex;flex-direction:column;align-items:center;gap:16px;padding:80px 20px;color:#73838e;font-size:14px;line-height:24px;background:#f1f4f7;}
@media(max-width:350px){.utr-hero{padding:12px 16px 16px;}.utr-rating-row{gap:8px;}.utr-rating-number{font-size:74px;}.utr-ntrp{width:90px;padding-left:14px;}.utr-ntrp-value{font-size:36px;}.utr-ranking-card{padding:17px 13px;gap:7px;}.utr-rank-number{font-size:29px;}.utr-body{padding:20px 13px 24px;}.utr-result{padding:0 12px;}.utr-result-value{font-size:25px;}}
</style>
