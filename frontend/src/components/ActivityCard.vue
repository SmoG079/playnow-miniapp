<script setup lang="ts">
import { go, dayLabel, type Activity } from '../data/fixtures'
import { usePrototype } from '../stores/prototype'
defineProps<{ item: Activity }>()
const store = usePrototype()
</script>
<template>
  <view class="activity-card" @click="go('activity', '?id=' + item.id)">
    <view class="row between"><view class="row gap8"><view class="club-monogram">{{ item.club.slice(0, 1) }}</view><text class="muted small">{{ item.club }}</text></view><wd-icon name="arrow-right" color="#8a9690" /></view>
    <text class="activity-title">{{ item.title }}</text>
    <view class="activity-body"><image :src="item.image" mode="aspectFill" class="activity-image" /><view class="activity-info"><text class="strong">{{ dayLabel(item.day) }} {{ item.time }}</text><text class="muted small">NTRP {{ item.level.toFixed(1) }} · {{ item.distance }}km</text><view class="row gap8"><text class="price">¥{{ item.price }}</text><text class="muted small">/ 人</text></view></view></view>
    <view class="row between activity-footer"><view class="row gap8"><view class="avatars"><text>林</text><text>陈</text><text>周</text></view><text class="small muted">{{ item.joined + (store.joinedIds.includes(item.id) ? 1 : 0) }}/{{ item.capacity }} 人</text></view><text :class="['join-label', { subdued: item.joined >= item.capacity }]">{{ store.joinedIds.includes(item.id) ? '已报名' : item.joined >= item.capacity ? '已满员' : '还差 ' + (item.capacity - item.joined) + ' 人' }} <wd-icon name="arrow-right" /></text></view>
  </view>
</template>
