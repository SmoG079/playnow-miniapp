<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { onHide } from "@dcloudio/uni-app";
import { useDiscovery } from "../stores/discovery";
import { suspendCustomTabBar } from "../utils/tabbar";
const location = useDiscovery(), visible = ref(false);
let restoreTabBar: (() => void) | undefined;
watch(visible, (open) => {
  if (open) restoreTabBar = suspendCustomTabBar();
  else { restoreTabBar?.(); restoreTabBar = undefined; }
}, { flush: "sync" });
function close() { visible.value = false; }
onHide(close);
onBeforeUnmount(close);
const emit = defineEmits<{ (e: "change"): void }>();
async function locate() {
  try { await location.locate(); visible.value = false; emit("change"); }
  catch { uni.showToast({ title: "定位未成功，请手动选择城市", icon: "none" }); }
}
function select(e: any) {
  location.selectRegion(e.detail.value, e.detail.code); visible.value = false; emit("change");
}
</script>
<template>
  <button class="city-pill" aria-label="选择当前城市" @click="visible = true">
    <wd-icon name="location" size="15px" color="#c8e6b8" /><text>{{ location.city || "城市" }}</text><wd-icon name="arrow-down" size="11px" />
  </button>
  <wd-popup v-model="visible" position="bottom" :z-index="200" closable safe-area-inset-bottom custom-style="border-radius:20px 20px 0 0">
    <view class="city-options"><text class="section-title">选择城市</text>
      <wd-button block :loading="location.locating" @click="locate">定位到当前城市</wd-button>
      <picker mode="region" :value="location.region" @change="select"><view class="filter-pill"><text>手动选择城市</text><wd-icon name="arrow-right" size="14px" /></view></picker>
    </view>
  </wd-popup>
</template>
