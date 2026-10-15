<script setup lang="ts">
import { ref } from "vue";
import { useDiscovery } from "../stores/discovery";
const discovery = useDiscovery();
const props=defineProps<{ city: string; locationName?: string; selected?: boolean; label?: string; hint?: string; field?: boolean; address?: string; disabled?: boolean }>();
const emit=defineEmits<{ (e:"busy",value:boolean):void; (e:"select",value:{city:string;location_name:string;latitude:number;longitude:number;address:string}):void }>();
const busy=ref(false);
function choose() {
  if (props.disabled || busy.value) return;
  uni.chooseLocation({
    success: async (point) => {
      busy.value=true; emit("busy",true);
      try {
        const city = await discovery.selectPoint(point);
        emit("select",{city,location_name:point.name,latitude:point.latitude,longitude:point.longitude,address:point.address||point.name});
      } catch (error: any) { uni.showToast({title:error.message || "城市识别失败，请重新选择地点",icon:"none"}); }
      busy.value=false; emit("busy",false);
    },
    fail: error => { if (!error.errMsg?.includes("cancel")) uni.showToast({title:"地图暂时不可用，请检查定位权限后重试",icon:"none"}); },
  });
}
</script>
<template>
  <view v-if="field"><view class="picker-field map-location-field" :class="{locked:disabled}" @click="choose"><text>{{ locationName || address || "在地图中选择" }}</text><wd-icon name="location" /></view><text v-if="locationName && address" class="location-address">{{ address }}</text><text class="muted small">{{ busy ? '正在识别城市…' : disabled ? '已关联球场' : (city ? city : '请选择地图位置') }}</text></view>
  <view v-else class="location-select"><wd-button variant="text" size="small" :loading="busy" :disabled="disabled" @click="choose">{{ selected ? "重新选择" + (label || "活动地点") : "选择" + (label || "活动地点") }}</wd-button><text v-if="hint">{{ hint }}</text></view>
</template>
<style scoped>.location-address{display:block;color:#849188;font-size:12px;line-height:1.6;margin:4px 0}.map-location-field text{flex:1;min-width:0;line-height:1.5}.map-location-field.locked{background:#f3f6f4;color:#647d70}.location-select{display:flex;align-items:center;flex-wrap:wrap;margin:-8px 0 16px;gap:8px}.location-select text{font-size:11px;color:#789084}</style>
