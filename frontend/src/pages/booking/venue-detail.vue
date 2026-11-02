<script setup lang="ts">
import AppShell from "../../components/AppShell.vue";
</script>
<template><AppShell back title="订场服务"><view class="content"><text class="section-title">订场服务暂未开放</text><text class="muted">俱乐部现以球友社群形式组织活动，场地由组织者自行安排。历史预约可在“我的预约”中查看和取消。</text><wd-button block @click="uni.switchTab({url:'/pages/booking/club-list'})">查看本地俱乐部</wd-button></view></AppShell></template>
