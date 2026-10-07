<script setup lang="ts">
import { ref, computed, watch } from "vue";
const props = defineProps<{
  src?: string;
  /** 本地打包的兜底图（/static/xxx.jpg），src 为空或加载失败时回退显示 */
  fallback?: string;
  width?: string;
  height?: string;
  round?: boolean;
  mode?: string;
}>();
const failed = ref(false);
const placeholder = props.round ? "user" : "image";

// 实际展示的图片：优先远程 src；为空或加载失败时回退到本地打包图
const displaySrc = computed(() => {
  if (props.src && !failed.value) return props.src;
  return props.fallback || "";
});

// src 变化时重置失败状态
watch(
  () => props.src,
  () => (failed.value = false),
);
</script>

<template>
  <view
    class="photo"
    :class="{ round }"
    :style="{ width: width || '100%', height: height || '100%' }"
  >
    <image
      v-if="displaySrc"
      class="photo-img"
      :src="displaySrc"
      :mode="mode || 'aspectFill'"
      :style="{ width: width || '100%', height: height || '100%' }"
      @error="failed = true"
    />
    <view v-else class="photo-ph">
      <wd-icon :name="placeholder" :size="width || '40px'" color="#c2d3cb" />
    </view>
  </view>
</template>

<style scoped>
.photo {
  overflow: hidden;
  background: #eef1ef;
}
.photo.round {
  border-radius: 50%;
}
.photo-img {
  display: block;
}
.photo-ph {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
