<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { onHide } from '@dcloudio/uni-app';
import { suspendCustomTabBar } from '../utils/tabbar';
import type { ChoiceOption, ChoiceValue } from '../domain/choices';
const props = withDefaults(defineProps<{
  modelValue: boolean;
  title: string;
  options: ChoiceOption[];
  value?: ChoiceValue | ChoiceValue[];
  multiple?: boolean;
}>(), { multiple: false });
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'select', value: ChoiceValue | ChoiceValue[]): void;
}>();
const visible = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) });
const draft = ref<ChoiceValue[]>([]);
let restoreTabBar: (() => void) | undefined;
function restore() { restoreTabBar?.(); restoreTabBar = undefined; }
watch(() => props.modelValue, open => {
  if (open) restoreTabBar = suspendCustomTabBar();
  else restore();
}, { flush:'sync' });
onHide(() => { visible.value = false; restore(); });
onBeforeUnmount(restore);
watch(() => props.modelValue, open => {
  if (open) draft.value = Array.isArray(props.value) ? [...props.value] : [];
});
const listHeight = computed(() => `min(60vh, ${props.options.reduce((height, option) => height + (option.description ? 108 : 72), 16)}px)`);
function selected(value: ChoiceValue) {
  return props.multiple ? draft.value.includes(value) : props.value === value;
}
function choose(option: ChoiceOption) {
  if (option.disabled) return;
  if (props.multiple) {
    draft.value = selected(option.value) ? draft.value.filter(value => value !== option.value) : [...draft.value, option.value];
  } else {
    emit('select', option.value);
    visible.value = false;
  }
}
function confirm() {
  emit('select', [...draft.value]);
  visible.value = false;
}
</script>
<template>
  <wd-popup v-model="visible" position="bottom" round root-portal :z-index="300" :safe-area-inset-bottom="true">
    <view class="choice-sheet">
      <view class="choice-handle" />
      <view class="choice-header"><text class="choice-title">{{ title }}</text><view class="choice-close" role="button" aria-label="关闭选择" @click="visible = false"><wd-icon name="close" size="22px" /></view></view>
      <scroll-view scroll-y class="choice-scroll" :style="{height:listHeight}">
        <view class="choice-list">
          <view v-for="option in options" :key="option.value" class="choice-option" :class="{'is-selected':selected(option.value),'is-disabled':option.disabled}" role="button" :aria-label="option.label + (selected(option.value) ? '，已选中' : '')" :aria-disabled="!!option.disabled" @click="choose(option)">
            <view class="choice-copy"><text class="choice-label">{{ option.label }}</text><text v-if="option.description" class="choice-description">{{ option.description }}</text></view>
            <view v-if="selected(option.value)" class="choice-check"><wd-icon name="check" size="18px" /></view>
          </view>
          <text v-if="!options.length" class="choice-empty">暂无可选项</text>
        </view>
      </scroll-view>
      <view v-if="multiple" class="choice-footer"><wd-button block @click="confirm">确定（已选 {{ draft.length }} 项）</wd-button></view>
    </view>
  </wd-popup>
</template>
<style scoped>
.choice-sheet{background:#fff;color:#203c2b;padding-top:10px}.choice-handle{width:36px;height:4px;border-radius:4px;background:#e0e7e2;margin:0 auto 8px}.choice-header{display:flex;align-items:center;justify-content:space-between;padding:14px 20px 18px;border-bottom:1px solid #edf1ee;gap:16px}.choice-title{font-size:21px;line-height:30px;font-weight:700}.choice-close{flex:none;width:36px;height:36px;border:1px solid #e3eae5;background:#f6f9f7;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#52695b}.choice-scroll{box-sizing:border-box}.choice-list{padding:8px 16px 16px}.choice-option{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:64px;box-sizing:border-box;padding:18px 16px;margin-top:6px;border:1px solid transparent;border-radius:14px}.choice-option.is-selected{background:#eaf4ee;border-color:#b7d6c3}.choice-copy{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px}.choice-label{font-size:16px;line-height:24px;font-weight:650;overflow-wrap:anywhere}.choice-description{font-size:13px;line-height:21px;color:#87968c;overflow-wrap:anywhere}.is-selected .choice-label{color:#126d4e}.is-selected .choice-description{color:#4f7962}.choice-check{width:25px;height:25px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#147553;color:#fff;flex:none}.is-disabled{opacity:.4}.choice-empty{display:block;padding:28px;text-align:center;color:#87968c;font-size:14px}.choice-footer{padding:12px 20px 16px;border-top:1px solid #edf1ee}
</style>
