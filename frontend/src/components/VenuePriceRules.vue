<script setup lang="ts">
import { ref, watch } from "vue";
import { request } from "../services/api";
import { businessDate } from "../utils/date";
const props = defineProps<{ modelValue: any[]; basePrice: string | number; clubId: number; venueId: number }>();
const emit = defineEmits<{ 'update:modelValue': [value:any[]] }>();
const rules = ref<any[]>([]), preview = ref<any[]>([]), date = ref(businessDate()), loading = ref(false);
const kinds = [{label:'指定日期',value:'date_range'},{label:'每周重复',value:'weekly'},{label:'每月重复',value:'monthly'},{label:'每天分时',value:'daily_time'}];
watch(() => props.modelValue, v => { rules.value = (v || []).map(r => ({...r, weekdays:r.weekdays ? [...r.weekdays] : undefined})); }, { immediate:true, deep:true });
let previewVersion=0;
function invalidatePreview() {previewVersion++;preview.value=[];loading.value=false;}
function changeDate(value:string) {date.value=value;invalidatePreview();}
function update() { invalidatePreview(); emit('update:modelValue',rules.value.map(r=>({...r}))); }
function add() { rules.value.unshift({type:'weekly',weekdays:[6,7],price:'',start_time:'',end_time:''}); update(); }
function move(i:number, delta:number) { const other=i+delta; if(other<0||other>=rules.value.length)return; [rules.value[i],rules.value[other]]=[rules.value[other],rules.value[i]]; update(); }
function changeKind(r:any,index:number) { r.type=kinds[index].value; delete r.start_date;delete r.end_date;delete r.weekdays;delete r.start_day;delete r.end_day; if(r.type==='weekly')r.weekdays=[6,7];if(r.type==='monthly'){r.start_day=1;r.end_day=7;}if(r.type==='date_range')r.start_date=r.end_date=businessDate();if(r.type==='daily_time'){r.start_time='08:00';r.end_time='10:00';} update(); }
function weekday(r:any,n:number) { const values=new Set<number>(r.weekdays||[]);values.has(n)?values.delete(n):values.add(n);r.weekdays=[...values].sort();update(); }
async function showPreview() {
  const version=++previewVersion;
  loading.value=true;
  try { const url=props.venueId?`/venues/${props.venueId}/prices/preview`:`/venues/with-club/${props.clubId}/prices/preview`;
    const result:any=await request(url,{method:'POST',data:{price_per_hour:props.basePrice,price_rules:rules.value,date:date.value}});if(version===previewVersion)preview.value=result.slots;
  } catch(e:any) { if(version===previewVersion)uni.showToast({title:e.message||'预览失败',icon:'none'}); } finally {if(version===previewVersion)loading.value=false;}
}
watch(() => props.basePrice, invalidatePreview);
</script>
<template>
  <view class="pricing-editor">
    <text class="section-title">特殊价格规则</text><text class="muted">按顺序匹配，靠前优先。新增规则置顶；无匹配时使用基础价。</text>
    <view v-for="(r,i) in rules" :key="i" class="rule-card">
      <view class="row between"><text class="strong">规则 {{ i+1 }}</text><view class="row"><wd-button size="small" variant="text" :disabled="i===0" @click="move(i,-1)">上移</wd-button><wd-button size="small" variant="text" :disabled="i===rules.length-1" @click="move(i,1)">下移</wd-button><wd-button size="small" variant="text" type="danger" @click="rules.splice(i,1);update()">删除</wd-button></view></view>
      <picker :value="Math.max(0,kinds.findIndex(k=>k.value===r.type || (r.type==='time_range' && k.value==='daily_time')))" :range="kinds.map(k=>k.label)" @change="changeKind(r,Number($event.detail.value))"><view class="picker-field">{{ kinds.find(k=>k.value===r.type)?.label || '每天分时' }}</view></picker>
      <view class="row between"><text>星期条件</text><wd-button v-if="r.type!=='weekly'" size="small" variant="text" @click="r.weekdays ? delete r.weekdays : r.weekdays=[6,7];update()">{{r.weekdays?'取消限定':'添加限定'}}</wd-button></view>
      <view v-if="r.weekdays" class="weekdays"><wd-button v-for="(label,n) in ['一','二','三','四','五','六','日']" :key="n" size="small" :type="r.weekdays?.includes(n+1)?'primary':'info'" @click="weekday(r,n+1)">{{label}}</wd-button></view>
      <view class="row between"><text>每月日期条件</text><wd-button v-if="r.type!=='monthly'" size="small" variant="text" @click="r.start_day!=null ? (delete r.start_day,delete r.end_day) : (r.start_day=1,r.end_day=7);update()">{{r.start_day!=null?'取消限定':'添加限定'}}</wd-button></view>
      <view v-if="r.start_day!=null" class="row"><text>每月</text><wd-input-number v-model="r.start_day" :min="1" :max="31" @change="update"/><text>至</text><wd-input-number v-model="r.end_day" :min="1" :max="31" @change="update"/><text>号</text></view>
      <view class="row between"><text>限定有效日期</text><wd-button v-if="r.type!=='date_range'" size="small" variant="text" @click="r.start_date ? (delete r.start_date,delete r.end_date) : (r.start_date=date,r.end_date=date);update()">{{ r.start_date ? '取消限定' : '添加限定' }}</wd-button></view>
      <view v-if="r.start_date" class="row"><picker mode="date" :value="r.start_date" @change="r.start_date=$event.detail.value;update()"><view class="picker-field">{{r.start_date}}</view></picker><text>至</text><picker mode="date" :value="r.end_date" @change="r.end_date=$event.detail.value;update()"><view class="picker-field">{{r.end_date}}</view></picker></view>
      <text class="muted">有限日期规则到期后自动移除，并发送系统通知。</text>
      <view class="row between"><text>生效时段（30分钟对齐）</text><wd-button v-if="!['daily_time','time_range'].includes(r.type)" size="small" variant="text" @click="r.start_time ? (r.start_time='',r.end_time='') : (r.start_time='08:00',r.end_time='10:00');update()">{{r.start_time?'改为全天':'设置时段'}}</wd-button></view>
      <view v-if="r.start_time" class="row"><picker mode="time" :value="r.start_time" @change="r.start_time=$event.detail.value;update()"><view class="picker-field">{{r.start_time}}</view></picker><text>至</text><picker mode="time" :value="r.end_time" @change="r.end_time=$event.detail.value;update()"><view class="picker-field">{{r.end_time}}</view></picker></view>
      <wd-input v-model="r.price" type="digit" placeholder="特殊价格（元/小时）" @input="update" />
    </view>
    <wd-button custom-class="add-price-rule-button" variant="plain" :disabled="rules.length>=100" @click="add">新增规则</wd-button>
    <view class="preview-section"><text class="strong">价格预览</text><picker mode="date" :value="date" @change="changeDate($event.detail.value)"><view class="picker-field">{{date}}</view></picker><wd-button custom-class="price-preview-button" :loading="loading" variant="plain" @click="showPreview">预览当前设置</wd-button><view v-for="s in preview" :key="s.start_time" class="row between"><text>{{s.start_time}}–{{s.end_time}}</text><text>¥{{s.price}} · {{s.rule_index==null?'基础价':`规则 ${s.rule_index+1}`}}（¥{{s.hourly_price}}/小时）</text></view></view>
  </view>
</template>
<style scoped>
.pricing-editor {display:flex;flex-direction:column;gap:12px;margin:20px 0;} .rule-card {border:1px solid #e5e8e5;border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:10px;} .weekdays {display:flex;flex-wrap:wrap;gap:6px;} .rule-card .row {flex-wrap:wrap;gap:6px;} .preview-section {display:flex;flex-direction:column;gap:12px;margin-top:16px;}
</style>
