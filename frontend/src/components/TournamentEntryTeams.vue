<script setup lang="ts">
import type { EntryTeam } from '../services/tournaments';
defineProps<{ teams: EntryTeam[]; selectable: boolean; ungrouped?: boolean; myUserId?: string; busy?: boolean }>();
const emit = defineEmits<{ select: [team: EntryTeam, seat: EntryTeam['seats'][number]] }>();
</script>
<template>
  <view class="entry-roster">
    <view v-for="(team,index) in teams" :key="team.id" class="entry-team">
      <view class="entry-heading"><text class="entry-title">{{ ungrouped ? '第 ' + (index + 1) + ' 队' : '第 ' + team.group_no + ' 组 · ' + team.position + ' 队' }}</text><text class="entry-count">{{ team.seats.filter(s => s.occupied).length }}/{{ team.seats.length }} 人</text></view>
      <view v-for="seat in team.seats" :key="seat.seat" class="entry-person" :class="{ 'entry-mine': seat.participant?.user_id === myUserId, 'entry-open': !seat.occupied && selectable && !busy }" role="button" :aria-label="seat.occupied ? seat.participant?.user_nickname || '已占位' : '选择第' + team.group_no + '组' + team.position + '队的空位报名'" @click="!seat.occupied && selectable && !busy && emit('select',team,seat)">
        <Photo v-if="seat.occupied" :src="seat.participant?.user_avatar" round width="42px" height="42px" />
        <view v-else class="entry-plus"><wd-icon name="plus" size="22px" color="#839087" /></view>
        <view class="entry-copy">
          <text class="entry-name">{{ seat.occupied ? (seat.participant ? seat.participant.user_nickname || '球友' : '已占位') : selectable ? '空位 · 点击报名' : '空位 · 等待报名' }}</text>
          <text v-if="seat.gender" class="entry-gender" :class="seat.gender">{{ seat.gender === 'male' ? '男' : '女' }}</text>
        </view>
        <text v-if="seat.occupied" class="entry-status">{{ seat.participant?.confirmed ? (seat.participant.user_id === myUserId ? '我' : '已报名') : '报名确认中' }}</text>
      </view>
    </view>
  </view>
</template>
<style scoped>
.entry-team{background:#fff;border:1px solid #e1e7e3;border-radius:16px;padding:14px 16px;margin-bottom:12px}
.entry-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:8px}
.entry-title{font-size:15px;font-weight:650;color:#203c2d}.entry-count{font-size:12px;color:#839087}
.entry-person{display:flex;align-items:center;gap:12px;padding:13px 0;border-top:1px solid #edf0ee;min-height:46px}
.entry-person.entry-mine{background:#f5fbf7}.entry-copy{flex:1;min-width:0}.entry-name{display:block;font-size:14px;line-height:1.5;overflow-wrap:anywhere;color:#243c2e}
.entry-status{flex-shrink:0;font-size:11px;color:#839087}.entry-plus{height:40px;width:40px;flex-shrink:0;border:1px dashed #aeb9b2;border-radius:50%;display:flex;align-items:center;justify-content:center}
.entry-open .entry-name{color:#839087}.entry-gender{display:inline-block;font-size:11px;margin-top:4px;border-radius:8px;padding:1px 7px;background:#edf5ff;color:#538ac3}.entry-gender.female{background:#fff0f5;color:#d66c96}
</style>
