<script setup lang="ts">
import { computed, watch } from "vue";
import { onShow } from "@dcloudio/uni-app";
import DiscoveryCityButton from "./DiscoveryCityButton.vue";
import { useDiscovery } from "../stores/discovery";
import { useWeather } from "../stores/weather";
import { backOrHome } from "../utils/navigation";
const props = withDefaults(defineProps<{ title: string; back?: boolean; context?: boolean }>(), { context: true });
const emit = defineEmits<{ (e: "cityChange"): void }>();
const location = useDiscovery();
const weather = useWeather();
const statusTop = Number(uni.getSystemInfoSync().statusBarHeight || 0);
let navTop = statusTop + 8, navHeight = 32, cityWidth = 180;
try {
  const capsule = uni.getMenuButtonBoundingClientRect();
  if (capsule?.height > 0 && capsule.top >= statusTop) {
    navTop = capsule.top; navHeight = capsule.height;
    cityWidth = Math.max(80, capsule.left - 40);
  }
} catch { /* H5 uses the same layout without a native capsule. */ }
const weatherLabel = computed(() => !location.city ? "选择地区查看天气"
  : weather.loading ? "天气加载中"
  : weather.current ? `${Math.round(weather.current.temperature)}°C` : "天气暂不可用");
const refreshWeather = () => { if (props.context) return weather.refresh(location.city, location.region[0] || ""); };
watch(() => [props.context, location.city, location.region[0]], refreshWeather, { immediate: true });
onShow(refreshWeather);
</script>
<template>
  <view class="home-header main-header" :class="{ 'main-header-back': back, 'main-header-simple': !context }" :style="{ paddingTop: navTop + 'px' }">
    <view v-if="context" class="header-nav" :style="{ height: navHeight + 'px', maxWidth: cityWidth + 'px' }">
      <DiscoveryCityButton @change="emit('cityChange')" />
    </view>
    <view class="header-heading" :style="!context ? { minHeight: navHeight + 'px', maxWidth: cityWidth + 'px' } : {}">
      <button v-if="back" class="header-back" aria-label="返回" @click="backOrHome"><wd-icon name="arrow-left" size="23px" /></button>
      <text class="page-title">{{ title }}</text>
    </view>
    <view v-if="context" class="header-context">
      <text>{{ location.city || '未选择地区' }}</text><text class="header-divider">·</text>
      <text :aria-label="weather.current ? '当前温度 ' + weatherLabel : weatherLabel">{{ weatherLabel }}</text>
    </view>
  </view>
</template>
