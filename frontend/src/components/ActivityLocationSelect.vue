<script setup lang="ts">
import { ref } from "vue";
import { request } from "../services/api";
const props=defineProps<{ city: string; selected?: boolean; label?: string; hint?: string }>();
const emit=defineEmits<{ (e:"busy",value:boolean):void; (e:"select",value:{city:string;latitude:number;longitude:number;address:string}):void }>();
const busy=ref(false);
function choose() {
  uni.chooseLocation({
    success: async (point) => {
      busy.value=true; emit("busy",true);
      let city=props.city;
      try {
        const result:any=await request(`/discovery/location-city?lat=${point.latitude}&lng=${point.longitude}`);
        city=result.city;
      } catch { uni.showToast({title:"请手动确认地点所在城市",icon:"none"}); }

      emit("select",{city,latitude:point.latitude,longitude:point.longitude,address:point.address||point.name});
      busy.value=false; emit("busy",false);
    },
    fail: error => { if (!error.errMsg?.includes("cancel")) uni.showToast({title:"地图不可用，可手动选择城市",icon:"none"}); },
  });
}
</script>
<template>
  <view class="location-select"><wd-button variant="text" size="small" :loading="busy" @click="choose">{{ selected ? "重新选择" + (label || "活动地点") : "选择" + (label || "活动地点") }}</wd-button><text>{{ hint || "选填，用于距离排序，不会预订场地" }}</text></view>
</template>
<style scoped>.location-select{display:flex;align-items:center;flex-wrap:wrap;margin:-8px 0 16px;gap:8px}.location-select text{font-size:11px;color:#789084}</style>
