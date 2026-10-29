<script setup lang="ts">
import ChoiceSelect from './ChoiceSelect.vue';
import type { PaymentMethod } from '../domain/activity-payment';
defineProps<{ modelValue: PaymentMethod; fee: number }>();
const emit = defineEmits<{ (e: 'update:modelValue', value: PaymentMethod): void }>();
const options=[
  {value:'offline',label:'线下付款',description:'报名无需线上支付，费用由组织者自行线下收取。'},
  {value:'online',label:'线上付款',description:'报名需完成微信支付，退费按活动规则处理。'},
];
</script>
<template>
  <view class="payment-select">
    <ChoiceSelect :model-value="modelValue" title="付款方式" :options="options" @update:model-value="emit('update:modelValue',$event as PaymentMethod)" />
    <text v-if="!(fee > 0)" class="payment-help">报名费为 0 时免费参加，无需付款。</text>
  </view>
</template>
<style scoped>
.payment-select{margin:6px 0 12px}.payment-help{display:block;margin-top:8px;font-size:12px;line-height:20px;color:#87968c}
</style>
