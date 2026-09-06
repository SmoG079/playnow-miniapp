<script setup lang="ts">
import AppShell from '../../components/AppShell.vue'
import { go } from '../../data/fixtures'
</script>
<template><AppShell active="chat"><view class="content"><view class="page-heading"><text class="eyebrow">STAY CONNECTED</text><text class="page-title">消息</text></view><view class="empty-state message-empty"><wd-icon name="message" size="48px" color="#137454" /><text class="section-title">还没有会话</text><text class="muted">聊天服务暂未开放</text><wd-button variant="soft" @click="go('home')">去广场找球友</wd-button></view></view></AppShell></template>
