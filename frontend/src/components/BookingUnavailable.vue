<script setup lang="ts">
import AppShell from "./AppShell.vue";
</script>
<template>
  <AppShell back title="订场服务">
    <view class="content service-state">
      <view class="service-icon"><wd-icon name="calendar-line" size="32px" /></view>
      <text class="section-title">订场服务暂未开放</text>
      <text class="body-copy">俱乐部现以球友社群形式组织活动，场地由组织者自行安排。</text>
      <wd-button block @click="uni.switchTab({url:'/pages/booking/club-list'})">查看本地俱乐部</wd-button>
      <view class="service-history"><text class="muted small">历史预约仍可查看和取消</text><wd-button block variant="plain" @click="uni.navigateTo({url:'/pages/profile/my-bookings'})">我的预约</wd-button></view>
    </view>
  </AppShell>
</template>
<style scoped>
.service-state { display:flex; flex-direction:column; gap:20px; padding-top:32px; }
.service-icon { display:flex; align-items:center; justify-content:center; width:64px; height:64px; border-radius:16px; background:var(--playnow-brand-soft); color:var(--playnow-brand); }
.service-history { display:flex; flex-direction:column; gap:12px; margin-top:12px; padding-top:24px; border-top:1px solid var(--playnow-card-border); }
</style>
