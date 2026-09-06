<script setup lang="ts">
import { computed, ref } from 'vue'
import AppShell from '../../components/AppShell.vue'
import ActivityCard from '../../components/ActivityCard.vue'
import { activities, dateLabel, go } from '../../data/fixtures'
import { filterActivities } from '../../domain/booking'
import { usePrototype } from '../../stores/prototype'
const store = usePrototype()
const kind = ref('match'), showFilter = ref(false), day = ref(-1), level = ref('')
const draftDay = ref(-1), draftLevel = ref('')
const filtered = computed(() => filterActivities([...store.published, ...activities], day.value, level.value, kind.value))
function openFilter() { draftDay.value = day.value; draftLevel.value = level.value; showFilter.value = true }
function apply() { day.value = draftDay.value; level.value = draftLevel.value; showFilter.value = false }
</script>
<template>
  <AppShell active="home">
    <view class="home-header"><view class="row between"><text class="brand">PlayNow<text class="brand-dot">.</text></text><text class="location"><wd-icon name="location" /> 杭州 · 示例城市</text></view><view class="row between greeting"><view><text class="eyebrow">GOOD GAME, GOOD DAY</text><text class="page-title">今天，球场见。</text></view><text class="date-stamp">{{ dateLabel(0) }}<text class="date-note">每一局，都尽兴</text></text></view></view>
    <view class="home-feature" @click="go('clubs')"><image src="/static/court.jpg" mode="aspectFill" /><view class="feature-scrim" /><view class="feature-copy"><text class="photo-label">球场示意</text><text class="feature-title">把好天气，留给网球</text><text class="feature-sub">找到附近好球场 <wd-icon name="arrow-right" /></text></view></view>
    <view class="content">
      <view class="row between section-head"><view class="text-tabs"><button :class="{ selected: kind === 'match' }" @click="kind = 'match'">约球广场</button><button :class="{ selected: kind === 'tournament' }" @click="kind = 'tournament'">比赛</button></view><text class="muted small">{{ filtered.length }} 场可见</text></view>
      <view class="filter-row"><wd-button size="small" variant="soft" @click="openFilter">{{ day < 0 ? '全部时间' : day === 0 ? '今天' : '明天' }} <wd-icon name="arrow-down" /></wd-button><wd-button size="small" variant="soft" @click="openFilter">{{ level ? 'NTRP ' + level : '球技等级' }} <wd-icon name="arrow-down" /></wd-button><button class="icon-button" aria-label="筛选活动" @click="openFilter"><wd-icon name="filter" size="20px" /></button></view>
      <ActivityCard v-for="item in filtered" :key="item.id" :item="item" />
      <view v-if="!filtered.length" class="empty-state"><wd-icon name="search" size="38px" /><text class="section-title">暂时没有合适的活动</text><text class="muted">换个时间或等级再看看</text><wd-button variant="text" @click="day = -1; level = ''">清除筛选</wd-button></view>
      <text class="end-note">找到同频球友，下次还一起打。</text>
    </view>
    <wd-popup v-model="showFilter" position="bottom" closable custom-class="prototype-sheet"><view class="sheet"><text class="section-title">找到适合你的那一局</text><text class="field-label">时间</text><view class="choices"><button v-for="(label, i) in ['不限', '今天', '明天']" :key="label" :class="{ chosen: draftDay === i - 1 }" @click="draftDay = i - 1">{{ label }}</button></view><text class="field-label">NTRP 球技等级</text><view class="choices"><button v-for="l in ['', '2.5', '3.0', '3.5', '4.0']" :key="l" :class="{ chosen: draftLevel === l }" @click="draftLevel = l">{{ l || '不限' }}</button></view><wd-button block @click="apply">查看活动</wd-button></view></wd-popup>
  </AppShell>
</template>
