<script setup lang="ts">
import { ref } from "vue";
import { useDiscovery } from "../stores/discovery";
const location = useDiscovery(), visible = ref(false);
const emit = defineEmits<{ (e: "change"): void }>();
async function locate() {
  try { await location.locate(); visible.value = false; emit("change"); }
  catch { uni.showToast({ title: "定位未成功，请手动选择城市", icon: "none" }); }
}
function select(e: any) {
  location.selectRegion(e.detail.value); visible.value = false; emit("change");
}
</script>
<template>
  <button class="city-pill" aria-label="选择当前城市" @click="visible = true">
    <wd-icon name="location" size="10px" /><text>{{ location.city || "城市" }}</text><wd-icon name="arrow-down" size="8px" />
  </button>
  <wd-popup v-model="visible" position="bottom" closable safe-area-inset-bottom custom-style="border-radius:20px 20px 0 0">
    <view class="city-options"><text class="section-title">选择城市</text>
      <wd-button block :loading="location.locating" @click="locate">定位到当前城市</wd-button>
      <picker mode="region" :value="location.region" @change="select"><view class="filter-pill"><text>手动选择城市</text><wd-icon name="arrow-right" size="14px" /></view></picker>
    </view>
  </wd-popup>
</template>
