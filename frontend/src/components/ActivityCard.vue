<script setup lang="ts">
import { computed } from "vue";
import Photo from "./Photo.vue";
import { cardSchedule, cardCapacity, cardState, type ActivityCardData, type ActivityKind } from "../domain/activity-card";
const props = defineProps<{ item: ActivityCardData; kind: ActivityKind }>();
const emit = defineEmits<{ (e: "open"): void }>();
const tournament = computed(() => props.kind === "tournament");
const typeLabel = computed(() => tournament.value ? "比赛" : props.item.venue_id === undefined ? "约球活动" : props.item.venue_id ? "定场约球" : "自由约球");
const schedule = computed(() => cardSchedule(props.item, props.kind));
const capacity = computed(() => cardCapacity(props.item, props.kind));
const state = computed(() => cardState(props.item, capacity.value, props.kind));
const resultCaption = computed(() => {
  const r=props.item.result_summary;
  return r ? `${r.score || ""} ${r.is_draw ? "平局" : r.winner ? r.winner + " 胜" : "已完赛"}${r.walkover ? "（弃权）" : ""}` : "";
});
const cover = computed(() => props.item.cover_image || props.item.images?.[0]);
const place = computed(() => props.item.address || props.item.club_name || props.item.city);
</script>
<template>
  <view class="play-card" :class="{ 'play-card-tournament': tournament, 'play-card-post': !tournament }">
    <view class="play-card-main" @click="emit('open')">
      <view class="card-topline">
        <wd-tag size="small" round variant="light" :color="tournament ? '#007ac2' : '#006633'" :bg-color="tournament ? '#e5f4ff' : '#e7f3e9'" :icon="tournament ? 'trophy' : 'user-group'">{{ typeLabel }}</wd-tag>
        <view class="event-state" :class="{ 'event-state-active': state.active }"><view v-if="state.active" class="state-dot" /><text>{{ state.label }}</text></view>
      </view>
      <text class="card-event-title">{{ item.title || '网球活动' }}</text>
      <view class="card-schedule">
        <view class="date-block"><text class="date-month">{{ schedule.month }}</text><text class="date-day">{{ schedule.day }}</text></view>
        <view class="schedule-copy"><text class="card-time">{{ schedule.timeLabel }}</text><text class="schedule-caption">{{ resultCaption || schedule.weekday }}{{ !tournament && item.user_nickname ? ' · ' + item.user_nickname + ' 发起' : '' }}{{ item.level_required ? ' · NTRP ' + item.level_required : '' }}</text></view>
        <view v-if="cover || tournament" class="card-thumbnail"><Photo :src="cover" fallback="/static/tennis.jpg" width="48px" height="40px" /></view>
        <view v-else class="post-court" aria-hidden="true"><view class="post-court-net" /><view class="court-ball" /></view>
      </view>
      <view class="card-place"><wd-icon :name="item.address ? 'location' : 'company'" size="13px" /><text class="card-place-text">{{ place || '地点待补充' }}</text></view>
      <view class="card-bottom">
        <view v-if="capacity" class="capacity-copy"><view class="capacity-numbers"><text class="capacity-count">{{ capacity.count }}</text><text class="capacity-total">/ {{ capacity.total }} 人已报名</text></view><view class="capacity-track"><view class="capacity-fill" :style="{ width: capacity.percent + '%' }" /></view></view>
        <text v-else class="card-number">{{ item.id ? '#' + item.id : '网球活动' }}</text>
        <view class="card-open"><text>查看{{ tournament ? '比赛' : '球局' }}</text><wd-icon name="arrow-right" size="12px" /></view>
      </view>
    </view>
    <slot />
  </view>
</template>
<style scoped>
.play-card {margin-bottom:12px;overflow:hidden;border:1px solid #e0e9e2;border-radius:14px;background:#fff;box-shadow:0 3px 10px rgba(25,63,42,.035);}
.play-card-main {height:176px;padding:12px;display:grid;grid-template-rows:18px 22px 44px 18px 26px;gap:6px;}
.card-topline,.card-bottom {display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;}
.event-state {display:flex;align-items:center;gap:5px;color:#7d8b81;font-size:11px;line-height:18px;flex-shrink:0;}
.event-state-active {color:#217647;font-weight:600;}.state-dot {width:5px;height:5px;border-radius:50%;background:#81b83d;}
.card-event-title {display:block;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:16px;font-weight:750;line-height:22px;color:#203c2b;}
.card-schedule {display:flex;align-items:center;gap:10px;padding:2px 8px;border-radius:8px;background:#f2f7ec;overflow:hidden;}
.date-block {width:36px;flex:none;display:flex;flex-direction:column;align-items:center;border-right:1px solid #d9e7d0;padding-right:8px;}
.date-month {font-size:9px;color:#6c8357;line-height:12px;}.date-day {font-size:22px;font-weight:800;color:#336d32;line-height:24px;}
.schedule-copy {flex:1;min-width:0;}.card-time {display:block;font-size:14px;font-weight:700;color:#2c5438;line-height:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.schedule-caption {display:block;font-size:10px;color:#738565;line-height:14px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}
.card-thumbnail {flex:none;border-radius:6px;overflow:hidden;}.post-court {position:relative;width:34px;height:34px;flex:none;border:1px solid #b3cb98;border-radius:4px;background:#e4efd6;}
.post-court::before {content:'';position:absolute;top:4px;right:7px;bottom:4px;left:7px;border:1px solid #b3cb98;}.post-court-net {position:absolute;left:0;right:0;top:50%;height:1px;background:#b3cb98;}.court-ball {position:absolute;right:1px;bottom:3px;width:8px;height:8px;border-radius:50%;background:#b9dc6c;}
.card-place {display:flex;align-items:center;gap:5px;font-size:11px;line-height:18px;color:#718174;min-width:0;}.card-place-text {flex:1;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}
.card-bottom {border-top:1px solid #edf1e9;padding-top:3px;}.capacity-copy {flex:1;max-width:145px;}.capacity-numbers {display:flex;align-items:baseline;gap:4px;}.capacity-count {font-size:15px;font-weight:750;color:#256c46;line-height:18px;}.capacity-total {font-size:10px;color:#83917f;}.capacity-track {height:2px;margin-top:3px;border-radius:4px;overflow:hidden;background:#e9efe2;}.capacity-fill {height:100%;background:linear-gradient(90deg,#248258,#a2cc59);}
.card-open {display:flex;align-items:center;gap:4px;flex:none;border-radius:14px;padding:5px 8px;color:#277348;background:#edf6e4;font-size:10px;font-weight:600;line-height:16px;}.card-number {font-size:11px;color:#8b978d;}
.play-card-post{border-color:#cfe4d4;border-left:3px solid #006633}.play-card-tournament{border-color:#cfe6f6;border-left:3px solid #0085ca}.play-card-tournament .card-schedule{background:#edf7ff}.play-card-tournament .date-block{border-color:#cbe3f5}.play-card-tournament .date-month,.play-card-tournament .schedule-caption{color:#638da8}.play-card-tournament .date-day,.play-card-tournament .card-time,.play-card-tournament .capacity-count,.play-card-tournament .event-state-active{color:#087fc0}.play-card-tournament .card-open{background:#e7f4fd;color:#087fc0}.play-card-tournament .capacity-fill{background:linear-gradient(90deg,#0085ca,#65c8ee)}.play-card-tournament .capacity-track{background:#e3f0f8}.play-card-tournament .state-dot{background:#0085ca}.play-card-post .state-dot{background:#006633}
@media (max-width:350px) {.card-schedule{gap:6px;}.card-thumbnail{display:none;}.card-time{font-size:13px;}}
</style>
