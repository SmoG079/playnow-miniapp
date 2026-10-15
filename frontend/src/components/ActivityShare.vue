<template>
  <!-- #ifdef MP-WEIXIN -->
  <view class="activity-share">
    <wd-button
      round
      open-type="share"
      icon="share-alt"
      custom-style="width:44px;min-width:44px;height:44px;padding:0;border:0;border-radius:50%;background:#42464b;color:#fff;font-size:21px"
    ><text class="share-label">分享活动</text></wd-button>
  </view>
  <!-- #endif -->
</template>
<style scoped>
.share-label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.activity-share{display:flex;align-items:center;flex:none}
</style>
