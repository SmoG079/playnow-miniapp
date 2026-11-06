<script setup lang="ts">
import { computed } from "vue";
import Photo from "./Photo.vue";
import { cardSchedule, cardCapacity, cardDetails, cardStatus, type ActivityCardData, type ActivityKind } from "../domain/activity-card";
const props = defineProps<{ item: ActivityCardData; kind: ActivityKind }>();
const emit = defineEmits<{ (e: "open"): void }>();
const tournament = computed(() => props.kind === "tournament");
const details = computed(() => cardDetails(props.item, props.kind));
const schedule = computed(() => cardSchedule(props.item, props.kind));
const capacity = computed(() => cardCapacity(props.item, props.kind));
const state = computed(() => cardStatus(props.item, props.kind));
const resultCaption = computed(() => {
  const r = props.item.result_summary;
  return r ? `${r.score || ""} ${r.is_draw ? "平局" : r.winner ? r.winner + " 胜" : "已完赛"}${r.walkover ? "（弃权）" : ""}` : "";
});
const cover = computed(() => props.item.cover_image || props.item.images?.[0]);
const participants = computed(() => (props.item.card_participants || []).slice(0, 3));
const extraPeople = computed(() => participants.value.length && capacity.value ? Math.max(0, capacity.value.count - participants.value.length) : 0);
const hostAvatar = computed(() => tournament.value ? (props.item.club_id ? props.item.club_avatar : props.item.organizer_avatar) : props.item.user_avatar);
</script>
<template>
  <view class="play-card" :class="{ 'play-card-tournament': tournament, 'play-card-post': !tournament }">
    <view class="play-card-main" hover-class="play-card-pressed" role="button" :aria-label="'查看' + (item.title || '网球活动')" @click="emit('open')">
      <view class="card-host">
        <view class="host-avatar"><Photo v-if="hostAvatar" :src="hostAvatar" width="30px" height="30px" round /><text v-else>{{ details.host.slice(0, 1) }}</text></view>
        <text class="host-name">{{ details.host }}</text><text class="host-caption">{{ tournament ? (item.club_id ? '俱乐部主办' : '个人主办') : '发起的球局' }}</text>
      </view>
      <view class="card-title-row">
        <text class="card-event-title">{{ item.title || '网球活动' }}</text>
        <view class="card-kind"><wd-tag size="medium" type="primary" variant="light" :icon="tournament ? 'trophy' : 'user-group'">{{ details.typeLabel }}</wd-tag></view>
      </view>
      <view class="card-schedule">
        <view class="card-thumbnail"><Photo :src="cover" :fallback="tournament ? '/static/tennis.jpg' : '/static/court.jpg'" /></view>
        <view class="schedule-copy">
          <text class="card-date">{{ schedule.dateLabel }}</text><text class="card-time">{{ schedule.timeLabel }}</text>
          <text class="card-place">{{ details.place }}</text><text v-if="details.address" class="card-address">{{ details.address }}</text>
        </view>
      </view>
      <view class="card-specs">
        <view class="card-middle"><view class="event-state" :class="{ 'event-state-active': state.active }"><view v-if="state.active" class="state-dot" /><text>{{ state.label }}</text></view><text v-if="resultCaption" class="card-result">{{ resultCaption }}</text><view v-if="details.tags.length" class="card-tags"><wd-tag v-for="tag in details.tags" :key="tag" size="small" variant="light">{{ tag }}</wd-tag></view></view>
        <view v-if="details.feeLabel" class="card-fee"><text class="fee-amount">{{ details.feeLabel }}</text><text v-if="details.feeSuffix" class="fee-unit">{{ details.feeSuffix }}</text></view>
      </view>
      <view class="card-bottom">
        <view class="card-people">
          <view v-if="participants.length" class="card-avatars"><view v-for="person in participants" :key="person.user_id" class="participant-avatar" :aria-label="person.user_nickname || '球友'"><Photo v-if="person.user_avatar" :src="person.user_avatar" width="24px" height="24px" round /><text v-else>{{ (person.user_nickname || '球友').slice(0, 1) }}</text></view><view v-if="extraPeople" class="participant-avatar extra-people">+{{ extraPeople }}</view></view>
          <view class="capacity-copy"><template v-if="capacity"><text class="capacity-count">{{ capacity.count }} / {{ capacity.total }} 人</text><text class="capacity-caption">已报名</text></template><text v-else class="card-number">{{ item.id ? '#' + item.id : '网球活动' }}</text></view>
        </view>
        <view class="card-open"><text>查看{{ tournament ? '比赛' : '球局' }}</text><view class="card-open-arrow"><wd-icon name="arrow-right" size="13px" /></view></view>
      </view>
    </view>
    <slot />
  </view>
</template>
<style scoped>
.play-card{margin-bottom:16px;overflow:hidden;border:1px solid var(--playnow-card-border);border-radius:var(--playnow-card-radius);background:#fff;color:var(--playnow-text);}
.play-card-main{padding:18px 16px 0;}.play-card-pressed{background:#fafcfb;}
.card-host{display:flex;align-items:center;gap:7px;min-width:0;min-height:30px;}.host-avatar{display:flex;align-items:center;justify-content:center;flex:none;width:30px;height:30px;border-radius:50%;overflow:hidden;background:var(--playnow-brand-soft);color:var(--playnow-brand);font-size:12px;font-weight:600;}.host-name{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px;font-weight:600;line-height:20px;}.host-caption{flex:none;font-size:12px;color:var(--playnow-muted);line-height:18px;}
.card-title-row{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:9px;margin:12px 0;min-width:0;}.card-event-title{flex:1 1 180px;min-width:0;font-size:18px;font-weight:600;line-height:27px;overflow-wrap:anywhere;}.card-kind{flex:none;}
.card-schedule{display:flex;align-items:center;gap:13px;min-width:0;}.card-thumbnail{position:relative;flex:none;width:96px;height:104px;border-radius:10px;overflow:hidden;}
.schedule-copy{flex:1;min-width:0;}.card-date{display:block;font-size:12px;font-weight:500;line-height:18px;}.card-time{display:block;margin:1px 0 9px;font-size:20px;font-weight:600;line-height:25px;overflow-wrap:anywhere;font-variant-numeric:tabular-nums;}.card-place{display:block;font-size:13px;font-weight:600;line-height:20px;overflow-wrap:anywhere;}.card-address{display:block;margin-top:3px;color:var(--playnow-muted);font-size:12px;line-height:17px;overflow-wrap:anywhere;}
.card-specs{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:12px 0;min-width:0;}.card-middle{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px;}.event-state{display:flex;align-items:center;gap:5px;color:var(--playnow-muted);font-size:12px;line-height:17px;}.event-state-active{color:var(--playnow-brand);}.state-dot{flex:none;width:5px;height:5px;border-radius:50%;background:var(--playnow-brand);}.card-result{font-size:12px;line-height:17px;color:var(--playnow-muted);overflow-wrap:anywhere;}.card-tags{display:flex;flex-wrap:wrap;gap:5px;min-width:0;}.card-fee{display:flex;align-items:baseline;gap:3px;flex:none;white-space:nowrap;}.fee-amount{color:var(--playnow-brand);font-size:20px;font-weight:600;line-height:26px;}.fee-unit{font-size:12px;color:var(--playnow-muted);line-height:16px;}
.card-bottom{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--playnow-card-border);padding:12px 0;min-width:0;}.card-people{display:flex;align-items:center;flex-wrap:wrap;gap:7px;min-width:0;}.card-avatars{display:flex;align-items:center;flex:none;}.participant-avatar{display:flex;align-items:center;justify-content:center;flex:none;box-sizing:border-box;width:28px;height:28px;border:2px solid #fff;border-radius:50%;overflow:hidden;background:#daeee0;color:var(--playnow-brand);font-size:12px;font-weight:600;}.participant-avatar+.participant-avatar{margin-left:-9px;}.extra-people{background:var(--playnow-brand-soft);font-size:12px;}.capacity-copy{display:flex;flex-direction:column;}.capacity-count{font-size:12px;font-weight:600;line-height:17px;}.capacity-caption,.card-number{font-size:12px;color:var(--playnow-muted);line-height:15px;}.card-open{display:flex;align-items:center;justify-content:center;gap:3px;flex:none;padding:10px 0 10px 8px;min-height:44px;border-radius:10px;background:transparent;color:var(--playnow-brand);font-size:13px;font-weight:600;line-height:20px;}
.card-open-arrow{display:flex;}
@media(max-width:350px){.play-card-main{padding:13px 11px 0;}.card-schedule{gap:10px;}.card-thumbnail{width:72px;height:102px;}.card-time{font-size:16px;}.card-open{padding:9px 8px;}.card-people{gap:5px;}.fee-amount{font-size:17px;}}
</style>
