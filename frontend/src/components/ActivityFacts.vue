<script setup lang="ts">
defineProps<{schedule:string;name:string;address?:string;canNavigate:boolean}>();
const emit=defineEmits<{(e:"navigate"):void}>();
</script>
<template>
  <view class="activity-facts">
    <view class="activity-fact"><text class="fact-label">时间</text><text class="fact-value">{{ schedule }}</text></view>
    <view class="activity-fact location-fact" :class="{'location-active':canNavigate}" @click="canNavigate && emit('navigate')">
      <text class="fact-label">地点</text>
      <view class="location-content"><text class="location-name">{{ name }}</text><text v-if="address" class="location-address">{{ address }}</text></view>
      <wd-icon v-if="canNavigate" name="arrow-right" size="19px" color="#222" />
    </view>
  </view>
</template>
<style scoped>
.activity-facts{margin:20px 0 24px;padding:0 16px;border-radius:16px;background:#fff;border:1px solid #e7ede9}.activity-fact{display:flex;align-items:center;gap:16px;min-height:64px;padding:18px 0;border-bottom:1px solid #edf0ed}.activity-fact:last-child{border-bottom:0}.fact-label{flex:none;font-size:14px;line-height:22px;color:#888}.fact-value{flex:1;text-align:right;font-size:15px;line-height:25px;font-weight:650;color:#202523;overflow-wrap:anywhere}.location-content{flex:1;min-width:0;text-align:right;display:flex;flex-direction:column;gap:5px}.location-name{display:block;font-size:16px;font-weight:650;color:#202523;line-height:25px;overflow-wrap:anywhere}.location-address{display:block;font-size:12px;color:#929792;line-height:20px;overflow-wrap:anywhere}.location-fact{gap:10px}
</style>
