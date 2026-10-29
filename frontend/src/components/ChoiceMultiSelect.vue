<script setup lang="ts">
import { computed, ref } from 'vue';
import ChoiceSheet from './ChoiceSheet.vue';
import type { ChoiceOption, ChoiceValue } from '../domain/choices';
const props=defineProps<{modelValue:ChoiceValue[];title:string;options:ChoiceOption[]}>();
const emit=defineEmits<{(e:'update:modelValue',value:ChoiceValue[]):void;(e:'change',value:ChoiceValue[]):void}>();
const open=ref(false);
const summary=computed(()=>props.options.filter(option=>props.modelValue.includes(option.value)).map(option=>option.label).join('、') || '请选择');
function select(value:ChoiceValue|ChoiceValue[]) {if(!Array.isArray(value))return;emit('update:modelValue',value);emit('change',value);}
</script>
<template><view class="choice-multi-select"><view class="choice-multi-trigger" role="button" :aria-label="title+'，'+summary" @click="open=true"><text>{{ title }}</text><view class="choice-multi-value"><text>{{ summary }}</text><wd-icon name="arrow-right" size="16px" /></view></view><ChoiceSheet v-model="open" :title="title" :options="options" :value="modelValue" multiple @select="select" /></view></template>
<style scoped>
.choice-multi-trigger{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:60px;padding:12px 0;box-sizing:border-box;border-bottom:1px solid #edf1ee;font-size:14px;color:#385444}.choice-multi-value{display:flex;align-items:center;gap:9px;color:#203c2b;min-width:0}.choice-multi-value text{text-align:right;overflow-wrap:anywhere;line-height:22px}
</style>
