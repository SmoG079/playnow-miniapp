<script setup lang="ts">
defineProps<{ nickname?: string; avatar?: string; level?: number | string | null }>();
</script>
<template><view class="participant-identity"><Photo round width="42px" height="42px" :src="avatar" /><view class="identity-copy"><text class="identity-name">{{ nickname || '球友' }}</text><text class="identity-level">{{ level != null ? 'NTRP ' + Number(level).toFixed(1) : '未定级' }}</text></view></view></template>
<style scoped>
.participant-identity{display:flex;align-items:center;gap:10px;flex:1;min-width:0;text-align:left}.identity-copy{flex:1;min-width:0}.identity-name{display:block;font-weight:600;font-size:14px;line-height:1.5;overflow-wrap:anywhere;color:#243c2e}.identity-level{display:inline-block;margin-top:5px;padding:2px 8px;border-radius:10px;background:#edf8f1;color:#159660;font-size:11px;line-height:16px}
</style>
