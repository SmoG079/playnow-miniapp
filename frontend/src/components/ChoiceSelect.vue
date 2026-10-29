<script setup lang="ts">
import { computed, ref } from 'vue';
import ChoiceSheet from './ChoiceSheet.vue';
import type { ChoiceOption, ChoiceValue } from '../domain/choices';
const props = withDefaults(defineProps<{ modelValue?: ChoiceValue; title: string; label?: string; options: ChoiceOption[]; placeholder?: string; disabled?: boolean }>(), { placeholder:'请选择', disabled:false });
const emit = defineEmits<{ (e:'update:modelValue', value:ChoiceValue):void; (e:'change', value:ChoiceValue):void }>();
const open=ref(false);
const current=computed(()=>props.options.find(option=>option.value===props.modelValue)?.label || props.placeholder);
function select(value:ChoiceValue | ChoiceValue[]) { if(Array.isArray(value))return; emit('update:modelValue',value);emit('change',value); }
</script>
<template>
  <view class="choice-select" :class="{'is-disabled':disabled}">
    <view class="choice-trigger" role="button" :aria-label="(label || title) + '，' + current" :aria-disabled="disabled" @click="!disabled && (open = true)">
      <slot :value="current"><view class="choice-field"><text class="choice-field-label">{{ label || title }}</text><view class="choice-field-value"><text>{{ current }}</text><wd-icon v-if="!disabled" name="arrow-right" size="16px" /></view></view></slot>
    </view>
    <ChoiceSheet v-model="open" :title="title" :options="options" :value="modelValue" @select="select" />
  </view>
</template>
<style scoped>
.choice-select{min-width:0}.choice-field{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:60px;padding:12px 0;box-sizing:border-box;border-bottom:1px solid #edf1ee}.choice-field-label{font-size:14px;font-weight:600;color:#385444;flex-shrink:0}.choice-field-value{display:flex;align-items:center;justify-content:flex-end;gap:9px;min-width:0;font-size:14px;line-height:22px;color:#203c2b}.choice-field-value text{overflow-wrap:anywhere;text-align:right}.is-disabled .choice-trigger{opacity:.55}
</style>
