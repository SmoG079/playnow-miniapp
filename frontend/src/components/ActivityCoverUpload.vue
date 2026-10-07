<script setup lang="ts">
import { ref } from "vue";
import Photo from "./Photo.vue";
import { uploadFile } from "../services/api";
const props = defineProps<{ modelValue: string[]; disabled?: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", value: string[]): void; (e: "busy", value: boolean): void }>();
const uploading = ref(false);
async function selectCover() {
  if (uploading.value || props.disabled) return;
  let selected: UniApp.ChooseImageSuccessCallbackResult;
  try {
    selected = await uni.chooseImage({ count: 1, sizeType: ["compressed"], sourceType: ["album", "camera"] });
  } catch { return; }
  const path = selected.tempFilePaths[0];
  if (!path) return;
  uploading.value = true;
  emit("busy", true);
  try {
    const result = await uploadFile(path, "post");
    const remaining = props.modelValue.filter((url) => url !== result.url);
    // Only cloud URLs enter the form. Temporary device paths are never persisted.
    emit("update:modelValue", [result.url, ...remaining].slice(0, 6));
  } catch {
    uni.showToast({ title: "封面上传失败，请重试", icon: "none" });
  } finally {
    uploading.value = false;
    emit("busy", false);
  }
}
</script>
<template>
  <view class="cover-upload">
    <view v-if="modelValue[0]" class="cover-image">
      <Photo :src="modelValue[0]" width="100%" height="180px" />
      <text class="cover-badge">封面</text>
    </view>
    <view v-else class="cover-placeholder" @click="selectCover">
      <wd-icon name="image" size="32px" />
      <text class="cover-title">为这场球局添一张封面</text>
      <text class="cover-hint">选填 · 图片直接上传云端</text>
    </view>
    <view class="cover-actions">
      <text class="cover-hint">首张图片作为封面 · 最多 6 张</text>
      <wd-button size="small" variant="plain" :loading="uploading" :disabled="disabled" @click="selectCover">{{ modelValue[0] ? "更换封面" : "上传封面" }}</wd-button>
    </view>
  </view>
</template>
<style scoped>
.cover-upload { margin-bottom: 24px; }
.cover-image { position: relative; border-radius: 16px; overflow: hidden; }
.cover-badge { position: absolute; left: 14px; bottom: 14px; padding: 4px 10px; background: rgba(0,0,0,.5); color: white; border-radius: 20px; font-size: 12px; }
.cover-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; min-height: 156px; border-radius: 16px; background: #edf4ef; color: #317957; }
.cover-title { font-size: 16px; font-weight: 600; }
.cover-hint { font-size: 12px; color: #85948b; }
.cover-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 12px; }
</style>
