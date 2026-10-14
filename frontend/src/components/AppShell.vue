<script setup lang="ts">
import MainHeader from "./MainHeader.vue";
defineProps<{ active?: string; back?: boolean; title?: string; simpleHeader?: boolean; flush?: boolean }>();
</script>
<template>
  <wd-config-provider>
    <view class="app-shell" :class="{'app-shell-flush':flush}">
      <MainHeader v-if="back" :title="title || '详情'" back :context="false" />
      <slot />
      <wd-toast />
      <wd-dialog />
    </view>
  </wd-config-provider>
</template>

<style scoped>
.app-shell-flush{padding-bottom:0;height:100vh;min-height:0;overflow:hidden}
.app-shell-flush :deep(.main-header){margin-bottom:0}
</style>
