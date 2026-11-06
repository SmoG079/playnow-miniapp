<script setup lang="ts">
const props = defineProps<{ title: string; content: string }>();
function show() { uni.showModal({title:props.title,content:props.content,showCancel:false,confirmText:'知道了'}); }
</script>
<template><view class="field-help" role="button" :aria-label="title + '说明'" @click.stop="show"><wd-icon name="question-circle" size="15px" color="var(--playnow-muted)" /></view></template>
<style scoped>.field-help{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;width:44px;min-width:44px;height:44px;flex:none;margin:-6px 0}</style>
