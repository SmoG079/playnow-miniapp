<script setup lang="ts">
import { ref } from "vue";
import { useDiscovery } from "../stores/discovery";
const discovery = useDiscovery();
const props=defineProps<{ city: string; selected?: boolean; label?: string; hint?: string; field?: boolean; address?: string; disabled?: boolean }>();
const emit=defineEmits<{ (e:"busy",value:boolean):void; (e:"select",value:{city:string;latitude:number;longitude:number;address:string}):void }>();
const busy=ref(false);
function choose() {
  if (props.disabled || busy.value) return;
  uni.chooseLocation({
    success: async (point) => {
      busy.value=true; emit("busy",true);
      try {
        const city = await discovery.selectPoint(point);
        emit("select",{city,latitude:point.latitude,longitude:point.longitude,address:point.address||point.name});
      } catch (error: any) { uni.showToast({title:error.message || "城市识别失败，请重新选择地点",icon:"none"}); }
      busy.value=false; emit("busy",false);
    },
    fail: error => { if (!error.errMsg?.includes("cancel")) uni.showToast({title:"地图暂时不可用，请检查定位权限后重试",icon:"none"}); },
  });
}
</script>
<template>
  <view v-if="field"><view class="picker-field map-location-field" :class="{locked:disabled}" @click="choose"><text>{{ address || "在地图中选择" }}</text><wd-icon name="location" /></view><text class="muted small">{{ busy ? '正在识别城市…' : disabled ? '地点随关联球场自动填写，不可修改' : (city ? city + ' · 城市根据地图位置自动填写' : '选择地图位置后自动获取城市') }}</text></view>
  <view v-else class="location-select"><wd-button variant="text" size="small" :loading="busy" :disabled="disabled" @click="choose">{{ selected ? "重新选择" + (label || "活动地点") : "选择" + (label || "活动地点") }}</wd-button><text>{{ hint || "选填，用于展示地点和距离排序，不会预订场地" }}</text></view>
</template>
<style scoped>.map-location-field text{flex:1;min-width:0;line-height:1.5}.map-location-field.locked{background:#f3f6f4;color:#647d70}.location-select{display:flex;align-items:center;flex-wrap:wrap;margin:-8px 0 16px;gap:8px}.location-select text{font-size:11px;color:#789084}</style>
