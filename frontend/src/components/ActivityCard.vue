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
const state = computed(() => cardState(props.item, capacity.value));
const cover = computed(() => props.item.cover_image || props.item.images?.[0]);
const place = computed(() => props.item.address || props.item.club_name || props.item.city);
</script>
<template>
  <view class="play-card" :class="{ 'play-card-tournament': tournament, 'play-card-post': !tournament }">
    <view class="play-card-main" @click="emit('open')">
      <view v-if="tournament" class="event-cover">
        <Photo :src="cover" fallback="/static/tennis.jpg" width="100%" height="100%" />
        <view class="cover-shade" />
        <view class="cover-type"><wd-icon name="trophy" size="14px" /><text>网球比赛</text></view>
        <view class="cover-schedule"><text class="cover-date">{{ schedule.dateLabel }}</text><text class="cover-time">{{ schedule.timeLabel }}</text></view>
        <view class="court-line" />
      </view>
      <view class="play-card-body">
        <view class="card-topline">
          <wd-tag size="small" round variant="light" :type="tournament ? 'primary' : 'success'" :icon="tournament ? 'trophy' : 'user-group'">{{ typeLabel }}</wd-tag>
          <view class="event-state" :class="{ 'event-state-active': state.active }"><view v-if="state.active" class="state-dot" /><text>{{ state.label }}</text></view>
        </view>
        <text class="card-event-title">{{ item.title || '网球活动' }}</text>
        <view v-if="!tournament" class="post-schedule">
          <view class="date-block"><text class="date-month">{{ schedule.month }}</text><text class="date-day">{{ schedule.day }}</text></view>
          <view class="schedule-copy"><text class="post-time">{{ schedule.timeLabel }}</text><text class="post-weekday">{{ schedule.weekday || '时间确定后一起上场' }}</text></view>
          <view v-if="cover" class="post-thumbnail"><Photo :src="cover" fallback="/static/tennis.jpg" width="60px" height="60px" /></view>
          <view v-else class="post-court" aria-hidden="true"><view class="post-court-net" /><view class="court-ball" /></view>
        </view>
        <view v-if="place" class="card-place"><wd-icon :name="item.address ? 'location' : 'company'" size="14px" /><text class="card-place-text">{{ place }}</text></view>
        <view v-if="!tournament && item.user_nickname" class="card-organizer"><Photo :src="item.user_avatar" round width="24px" height="24px" /><text class="card-organizer-name">{{ item.user_nickname }}</text><text class="organizer-label">发起</text><text v-if="item.level_required" class="level-chip">NTRP {{ item.level_required }}</text></view>
        <view v-else-if="!tournament && item.level_required" class="card-level">NTRP {{ item.level_required }}</view>
        <view class="card-bottom">
          <view v-if="capacity" class="capacity-copy"><view class="capacity-numbers"><text class="capacity-count">{{ capacity.count }}</text><text class="capacity-total">/ {{ capacity.total }} 人已报名</text></view><view class="capacity-track"><view class="capacity-fill" :style="{ width: capacity.percent + '%' }" /></view></view>
          <text v-else class="card-number">{{ item.id ? '#' + item.id : '网球活动' }}</text>
          <view class="card-open"><text>查看{{ tournament ? '比赛' : '球局' }}</text><wd-icon name="arrow-right" size="13px" /></view>
        </view>
      </view>
    </view>
    <slot />
  </view>
</template>
<style scoped>
.play-card { margin-bottom: 16px; overflow: hidden; border: 1px solid #e0e9e2; border-radius: 18px; background: #fff; box-shadow: 0 5px 16px rgba(25,63,42,.035); }
.play-card-body { padding: 16px; }
.event-cover { position: relative; height: 156px; overflow: hidden; background: #315e43; }
.cover-shade { position: absolute; top: 0; right: 0; bottom: 0; left: 0; background: linear-gradient(180deg,rgba(9,36,22,.12) 15%,rgba(9,36,22,.08) 35%,rgba(9,36,22,.8) 100%); }
.cover-type { position: absolute; left: 14px; top: 14px; display: flex; align-items: center; gap: 5px; padding: 5px 9px; border: 1px solid rgba(255,255,255,.3); border-radius: 20px; background: rgba(16,50,31,.65); color: #eff8d5; font-size: 11px; font-weight: 600; }
.cover-schedule { position: absolute; left: 16px; right: 16px; bottom: 16px; color: white; }
.cover-date { display: block; font-size: 12px; font-weight: 550; color: #e8f2e9; margin-bottom: 5px; }
.cover-time { display: block; font-size: 25px; line-height: 1.2; font-weight: 750; letter-spacing: -.3px; }
.court-line { position: absolute; right: 16px; top: 18px; width: 34px; height: 3px; border-radius: 4px; transform: rotate(-32deg); background: #c2e879; }
.card-topline { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.event-state { display: flex; align-items: center; gap: 5px; color: #7d8b81; font-size: 11px; line-height: 18px; flex-shrink: 0; }
.event-state-active { color: #217647; font-weight: 600; }
.state-dot { width: 5px; height: 5px; border-radius: 50%; background: #81b83d; }
.card-event-title { display: block; margin: 12px 0; font-size: 18px; font-weight: 750; line-height: 1.45; color: #203c2b; overflow-wrap: anywhere; }
.post-schedule { display: flex; align-items: center; gap: 12px; padding: 11px; margin-bottom: 14px; border-radius: 12px; background: #f2f7ec; }
.date-block { width: 44px; flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center; border-right: 1px solid #d9e7d0; padding-right: 10px; }
.date-month { font-size: 10px; color: #6c8357; line-height: 1.5; }
.date-day { font-size: 26px; font-weight: 800; color: #336d32; line-height: 1.15; }
.schedule-copy { flex: 1; min-width: 0; }
.post-time { display: block; font-size: 16px; font-weight: 700; color: #2c5438; line-height: 1.4; overflow-wrap: anywhere; }
.post-weekday { display: block; margin-top: 4px; font-size: 11px; color: #738565; }
.post-thumbnail { flex: none; border-radius: 9px; overflow: hidden; }
.post-court { position: relative; width: 48px; height: 54px; flex: none; border: 1px solid #b3cb98; border-radius: 5px; transform: rotate(7deg); background: #e4efd6; }
.post-court::before { content: ''; position: absolute; top: 5px; right: 10px; bottom: 5px; left: 10px; border: 1px solid #b3cb98; }
.post-court-net { position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: #b3cb98; }
.court-ball { position: absolute; right: -4px; bottom: 5px; width: 13px; height: 13px; border-radius: 50%; border: 2px solid #fff; background: #b9dc6c; }
.card-place { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; line-height: 1.6; color: #718174; }
.card-place-text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.card-organizer { display: flex; align-items: center; gap: 7px; margin-top: 13px; color: #526b59; font-size: 12px; }
.card-organizer-name { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; max-width: 120px; }
.organizer-label { color: #96a094; font-size: 10px; flex: none; }
.level-chip,.card-level { color: #6c7c47; background: #f3f5e8; font-size: 10px; border-radius: 5px; padding: 3px 6px; }
.level-chip { margin-left: auto; flex: none; max-width: 110px; overflow-wrap: anywhere; }
.card-level { display: inline-block; margin-top: 10px; }
.card-bottom { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-top: 1px solid #edf1e9; padding-top: 13px; margin-top: 14px; }
.capacity-copy { flex: 1; max-width: 156px; }
.capacity-numbers { display: flex; align-items: baseline; gap: 5px; }
.capacity-count { font-size: 19px; font-weight: 750; color: #256c46; line-height: 1.2; }
.capacity-total { font-size: 11px; color: #83917f; }
.capacity-track { height: 3px; margin-top: 7px; border-radius: 4px; overflow: hidden; background: #e9efe2; }
.capacity-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg,#248258,#a2cc59); }
.card-open { display: flex; align-items: center; gap: 6px; flex: none; border-radius: 20px; padding: 8px 10px; color: #277348; background: #edf6e4; font-size: 11px; font-weight: 600; }
.card-number { font-size: 11px; color: #8b978d; }
@media (max-width: 350px) { .play-card-body { padding: 14px; }.post-schedule { gap: 8px; padding: 9px; }.post-time { font-size: 14px; }.post-court { width: 32px; height: 44px; }.post-thumbnail { display: none; }.cover-time { font-size: 22px; }.card-event-title { font-size: 17px; } }
</style>
