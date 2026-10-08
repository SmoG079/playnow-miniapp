<script setup lang="ts">
defineProps<{ title: string }>();
const statusTop = Number(uni.getSystemInfoSync().statusBarHeight || 24) + 12;
</script>
<template>
  <view class="home-header main-header" :style="{ paddingTop: statusTop + 'px' }">
    <text class="brand">PlayNow<text class="brand-dot">.</text></text>
    <text class="page-title">{{ title }}</text>
  </view>
</template>
