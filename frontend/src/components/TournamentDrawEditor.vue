<script setup lang="ts">
import { ref, computed, getCurrentInstance } from "vue";
import { swapSeats, seatError, type DrawSeat } from "../domain/draw-adjustment";
import { teamName, type Tournament } from "../services/tournaments";
const props=defineProps<{ tournament:Tournament; busy:boolean }>();
const emit=defineEmits<{ cancel:[]; save:[data:{expected_version:number;idempotency_key:string;reason:string;positions:DrawSeat[]}] }>();
const original=(props.tournament.draw_positions||[]).map(s=>({...s}));
const seats=ref(original.map(s=>({...s}))), reason=ref(''), selected=ref(-1), dragging=ref(-1);
const version=props.tournament.draw_version, instance=getCurrentInstance();
const knockout=props.tournament.matches.some(m=>m.kind==='knockout');
const groups=[...new Set(original.map(s=>s.group_no))];
const error=computed(()=>seatError(original,seats.value,knockout));
const name=(id:number|null)=>id==null?'轮空':teamName(props.tournament.teams,id,props.tournament.registrations);
const dragPoint=ref({x:0,y:0});
let rects:any[]=[];
let scrollTop=0, lastScroll=0;
const windowHeight=uni.getSystemInfoSync().windowHeight;
function measureSeats() {
  uni.createSelectorQuery().in(instance?.proxy).selectAll('.draw-seat').boundingClientRect((data:any)=>{rects=data||[];}).exec();
}
function select(i:number) {if(props.busy)return;if(selected.value<0)selected.value=i;else {seats.value=swapSeats(seats.value,selected.value,i);selected.value=-1;}}
function start(i:number,event:any) {
  if(props.busy)return;
  dragging.value=i;selected.value=-1;
  const touch=event.detail?.touches?.[0]||event.touches?.[0]||event.detail?.changedTouches?.[0]||event.changedTouches?.[0];if(touch)dragPoint.value={x:touch.clientX,y:touch.clientY};
  measureSeats();
  uni.createSelectorQuery().selectViewport().scrollOffset((data:any)=>{scrollTop=data?.scrollTop||0;}).exec();
}
function move(event:any) {
  if(dragging.value<0)return;
  const touch=event.detail?.touches?.[0]||event.touches?.[0];
  if(!touch)return;
  dragPoint.value={x:touch.clientX,y:touch.clientY};
  const delta=touch.clientY<110?-50:touch.clientY>windowHeight-110?50:0;
  if(delta && Date.now()-lastScroll>120) {
    lastScroll=Date.now();scrollTop=Math.max(0,scrollTop+delta);
    uni.pageScrollTo({scrollTop,duration:0,success:measureSeats});
  }
}
function end(event:any) {
  if(dragging.value<0)return;
  const touch=event.detail?.changedTouches?.[0]||event.changedTouches?.[0];const point=touch?{x:touch.clientX,y:touch.clientY}:dragPoint.value;
  const target=rects.findIndex(r=>point.x>=r.left&&point.x<=r.right&&point.y>=r.top&&point.y<=r.bottom);
  if(target>=0&&target!==dragging.value)seats.value=swapSeats(seats.value,dragging.value,target);
  dragging.value=-1;rects=[];
}
const requestKey=`adjust-${Date.now()}-${Math.random().toString(36).slice(2)}`;
function save() {
  if(error.value||!reason.value.trim())return uni.showToast({title:error.value||'请填写调整原因',icon:'none'});
  if(JSON.stringify(original)===JSON.stringify(seats.value))return uni.showToast({title:'请先调整对位',icon:'none'});
  emit('save',{expected_version:version,idempotency_key:requestKey,reason:reason.value.trim(),positions:seats.value.map(s=>({...s}))});
}
</script>
<template>
  <view class="draw-editor">
    <text class="section-title">调整对位 · v{{version}}</text><text class="muted">拖动右侧手柄交换位置，也可依次点选两个位置。双打整队交换；跨组须保持各组人数。保存后需重新发布。</text>
    <view v-for="group in groups" :key="group" class="draw-group"><text class="strong">第 {{group}} 组</text>
      <template v-for="(seat,i) in seats" :key="`${seat.group_no}:${seat.position}`"><view v-if="seat.group_no===group" class="draw-seat" :class="{'seat-selected':selected===i,'seat-dragging':dragging===i}" @click="select(i)"><text>{{ knockout ? `第 ${Math.floor(seat.position/2)+1} 场 · ${seat.position%2?'B':'A'}` : `签位 ${seat.position+1}` }} · {{name(seat.team_id)}}</text><view class="drag-handle" @touchstart.stop="start(i,$event)" @touchmove.stop.prevent="move" @touchend.stop="end" @touchcancel.stop="dragging=-1" @click.stop>☰</view></view></template>
    </view>
    <text v-if="error" class="error-copy">{{error}}</text>
    <wd-textarea v-model="reason" :maxlength="256" placeholder="调整原因（必填）" />
    <view class="row"><wd-button variant="plain" :disabled="busy" @click="emit('cancel')">取消</wd-button><wd-button custom-class="save-draw-adjustment-button" :loading="busy" :disabled="!!error" @click="save">保存调整草稿</wd-button></view>
    <view v-if="dragging>=0" class="drag-preview" :style="{left:dragPoint.x+'px',top:dragPoint.y+'px'}">{{name(seats[dragging].team_id)}}</view>
  </view>
</template>
<style scoped>
.draw-editor {padding:16px;background:#fff;border:1px solid #e5e8e5;border-radius:16px;display:flex;flex-direction:column;gap:12px;} .draw-group {display:flex;flex-direction:column;gap:8px;} .draw-seat {display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border:1px solid #dce5df;border-radius:8px;min-height:44px;} .seat-selected {background:#e6f5eb;border-color:#147553;} .seat-dragging {opacity:.4;} .drag-handle {padding:12px;touch-action:none;} .drag-preview {position:fixed;transform:translate(-50%,-130%);z-index:1000;padding:12px;background:#147553;color:white;border-radius:8px;pointer-events:none;} .error-copy {color:#c74242;}
</style>
