<script setup lang="ts">
import { backOrHome } from "../utils/navigation";
defineProps<{ active?: string; back?: boolean; title?: string }>();
</script>
<template>
  <wd-config-provider>
    <view class="app-shell">
      <view v-if="back" class="topbar"
        ><button class="icon-button" aria-label="返回" @click="backOrHome">
          <wd-icon name="arrow-left" size="22px" /></button
        ><text class="topbar-title">{{ title }}</text
        ><view class="topbar-spacer"
      /></view>
      <slot />
      <wd-toast />
      <wd-dialog />
    </view>
  </wd-config-provider>
</template>
