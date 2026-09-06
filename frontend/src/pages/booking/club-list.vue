<script setup lang="ts">
import { computed, ref } from 'vue'
import AppShell from '../../components/AppShell.vue'
import { clubs, go } from '../../data/fixtures'
const search = ref(''), order = ref('distance')
const list = computed(() => clubs.filter(c => (c.name + c.area).includes(search.value)).slice().sort((a,b) => order.value === 'distance' ? a.distance - b.distance : a.price - b.price))
</script>
<template>
  <AppShell active="clubs"><view class="content"><view class="row between page-heading"><view><text class="eyebrow">FIND YOUR COURT</text><text class="page-title">下一场，就在附近</text></view><wd-icon name="location" size="28px" color="#137454" /></view><text class="muted">杭州 · 示例场馆</text><view class="search-wrap"><wd-input v-model="search" placeholder="搜索球场、区域" prefix-icon="search" clearable /></view><view class="row between section-head"><text class="strong">{{ list.length }} 家球场</text><wd-button size="small" variant="text" @click="order = order === 'distance' ? 'price' : 'distance'">{{ order === 'distance' ? '距离最近' : '价格最低' }} <wd-icon name="arrow-down" /></wd-button></view>
    <view v-for="club in list" :key="club.id" class="venue-card" @click="go('venue', '?id=' + club.id)"><view class="venue-photo"><image :src="club.image" mode="aspectFill" /><text class="photo-badge">示例场馆</text><text class="distance-badge">{{ club.distance }} km</text></view><view class="venue-card-body"><view class="row between"><text class="section-title">{{ club.name }}</text><text class="price">¥{{ club.price }}<text class="muted small"> 起/小时</text></text></view><text class="muted small">{{ club.area }}</text><view class="row between"><view class="row gap8"><text v-for="label in club.labels" :key="label" class="tag">{{ label }}</text></view><text class="link small">查看时段 <wd-icon name="arrow-right" /></text></view></view></view>
    <view v-if="!list.length" class="empty-state"><text class="section-title">没有找到球场</text><text class="muted">试试其他名称或区域</text></view><text class="end-note">场馆与价格仅用于原型演示</text></view></AppShell>
</template>
