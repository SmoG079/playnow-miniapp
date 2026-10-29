<script setup lang="ts">
import ChoiceSelect from './ChoiceSelect.vue';
const props = withDefaults(defineProps<{range:string[];value?:number;title?:string;disabled?:boolean}>(),{value:0,title:'请选择',disabled:false});
const emit = defineEmits<{(e:'change',event:{detail:{value:number}}):void}>();
</script>
<template>
  <ChoiceSelect :model-value="value" :title="title" :options="range.map((label,index)=>({label,value:index}))" :disabled="disabled" @change="emit('change',{detail:{value:Number($event)}})"><slot /></ChoiceSelect>
</template>
