<script setup lang="ts">
import { useDiscovery } from "../stores/discovery";
const props = defineProps<{ modelValue: string; label?: string }>();
const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();
const discovery = useDiscovery();
function change(e: any) { discovery.selectRegion(e.detail.value); emit("update:modelValue", discovery.city); }
</script>
<template>
  <view class="city-field">
    <text class="field-label">{{ label || "活动城市 *" }}</text>
    <picker mode="region" :value="discovery.region" @change="change">
      <view class="picker-field">{{ props.modelValue || "请选择活动所在城市" }}<wd-icon name="arrow-down" size="14px" /></view>
    </picker>
  </view>
</template>
<style scoped>.picker-field{display:flex;align-items:center;justify-content:space-between}.city-field{margin-bottom:16px}</style>
