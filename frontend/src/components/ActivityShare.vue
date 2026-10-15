<script setup lang="ts">
import { guideTimelineShare } from "../utils/share";
</script>
<template>
  <!-- #ifdef MP-WEIXIN -->
  <view class="activity-share">
    <wd-button size="small" variant="plain" open-type="share">分享给好友 / 群聊</wd-button>
    <wd-button size="small" variant="text" @click="guideTimelineShare">分享到朋友圈</wd-button>
  </view>
  <!-- #endif -->
</template>
<style scoped>
.activity-share{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0 20px}
</style>
