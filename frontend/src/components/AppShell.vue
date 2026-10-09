<script setup lang="ts">
import MainHeader from "./MainHeader.vue";
defineProps<{ active?: string; back?: boolean; title?: string; simpleHeader?: boolean }>();
</script>
<template>
  <wd-config-provider>
    <view class="app-shell">
      <MainHeader v-if="back" :title="title || '详情'" back :context="!simpleHeader" />
      <slot />
      <wd-toast />
      <wd-dialog />
    </view>
  </wd-config-provider>
</template>
