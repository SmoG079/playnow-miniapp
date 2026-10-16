<script setup lang="ts">
import { ref } from "vue";
import Photo from "./Photo.vue";
import FieldHelp from "./FieldHelp.vue";
import { uploadedImage, chooseImagePaths } from "../services/media";
const props = defineProps<{ modelValue: string[]; disabled?: boolean }>();
const emit = defineEmits<{ (e: "update:modelValue", value: string[]): void; (e: "busy", value: boolean): void }>();
const uploading = ref(false);
async function selectCover() {
  if (uploading.value || props.disabled) return;
  uploading.value = true;
  emit("busy", true);
  try {
    const [path] = await chooseImagePaths(1);
    if (!path) return;
    const url = await uploadedImage(path, "post");
    emit("update:modelValue", [url, ...props.modelValue.filter(item => item !== url)].slice(0, 6));
  } catch (error:any) {
    if (!error?.errMsg?.includes("cancel")) uni.showToast({ title: error.message || "封面上传失败，请重试", icon: "none" });
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
    </view>
    <view class="cover-actions">
      <view class="cover-label"><text>活动封面（选填）</text><FieldHelp title="活动封面" content="最多上传六张活动图片，第一张用作封面。您可以在活动图片中调整封面。" /></view>
      <wd-button size="small" variant="plain" :loading="uploading" :disabled="disabled" @click="selectCover">{{ modelValue[0] ? "更换封面" : "上传封面" }}</wd-button>
    </view>
  </view>
</template>
<style scoped>
.cover-upload { margin-bottom:16px;padding:16px;border:1px solid #e1e7e3;border-radius:18px;background:#fff; }
.cover-label{display:flex;align-items:center;font-size:13px;color:#586e60}
.cover-image { position: relative; border-radius: 16px; overflow: hidden; }
.cover-badge { position: absolute; left: 14px; bottom: 14px; padding: 4px 10px; background: rgba(0,0,0,.5); color: white; border-radius: 20px; font-size: 12px; }
.cover-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; min-height: 156px; border-radius: 16px; background: #edf4ef; color: #317957; }
.cover-title { font-size: 16px; font-weight: 600; }
.cover-hint { font-size: 12px; color: #85948b; }
.cover-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 12px; }
</style>
