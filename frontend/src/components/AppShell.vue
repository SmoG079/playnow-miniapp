<script setup lang="ts">
import type { ConfigProviderThemeVars } from "@wot-ui/ui";
import { getCurrentInstance, onMounted } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { syncCustomTabBarSelection } from "../utils/tabbar";
import MainHeader from "./MainHeader.vue";
import { isTimelinePreview } from "../utils/share";
const props = defineProps<{ active?: string; back?: boolean; title?: string; simpleHeader?: boolean; flush?: boolean }>();
// ConfigProvider resets semantic colors on its own root; configure that root explicitly.
const themeVars: ConfigProviderThemeVars = {
  primary1: "var(--playnow-brand-soft)",
  primary2: "#d3e6db",
  primary6: "var(--playnow-brand)",
  primary7: "#105c42",
  textMain: "var(--playnow-text)",
  textSecondary: "var(--playnow-muted)",
};
const instance = getCurrentInstance();
function syncTab() { syncCustomTabBarSelection(props.active, (instance?.proxy?.$root as any)?.$scope); }
onShow(syncTab);
onMounted(syncTab);
</script>
<template>
  <wd-config-provider :theme-vars="themeVars">
    <view class="app-shell" :class="{'app-shell-flush':flush}">
      <MainHeader v-if="back" :title="title || '详情'" :back="!isTimelinePreview()" :context="false" />
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
