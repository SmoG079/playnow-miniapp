<script setup lang="ts">
import { ref } from 'vue'
import AppShell from '../../components/AppShell.vue'
import { dateLabel, clubs, go } from '../../data/fixtures'
import { usePrototype } from '../../stores/prototype'
const store = usePrototype(), mode = ref('free'), title = ref(''), day = ref(0), start = ref('19:00'), end = ref('21:00'), level = ref('3.0'), players = ref(4), price = ref(''), club = ref(0), error = ref(''), done = ref(false)
function publish() {
  error.value = ''
  if (!title.value.trim()) { error.value = '请填写约球标题'; return }
  if (end.value <= start.value) { error.value = '结束时间必须晚于开始时间'; return }
  if (!price.value.trim() || !Number.isFinite(Number(price.value)) || Number(price.value) < 0) { error.value = '请填写有效的人均费用，免费请填 0'; return }
  if (done.value) return
  store.published.unshift({ id: Date.now(), title: title.value.trim(), club: mode.value === 'venue' ? clubs[club.value].name + ' · 示例' : '自由约球 · 地点待协商', day: day.value, time: start.value + '–' + end.value, level: Number(level.value), distance: mode.value === 'venue' ? clubs[club.value].distance : 0, price: Number(price.value), capacity: players.value, joined: 1, kind: 'match', image: '/static/tennis.jpg' })
  done.value = true
}
</script>
<template>
  <AppShell active="publish"><view class="content publish-content"><view class="page-heading"><text class="eyebrow">MAKE THE NEXT GAME</text><text class="page-title">好球局，由你发起</text><text class="muted subtitle">找到同频的人，一起上场。</text></view><view class="mode-switch"><button :class="{ chosen: mode === 'free' }" @click="mode = 'free'">自由约球</button><button :class="{ chosen: mode === 'venue' }" @click="mode = 'venue'">关联场地</button></view><text class="field-label">给这场球起个名字 <text class="required">*</text></text><wd-input v-model="title" placeholder="例如：周五下班，一起打双打" :maxlength="40" clearable /><text class="field-label">哪天上场</text><view class="date-options"><button v-for="(label,i) in ['今天','明天','后天']" :key="label" :class="{ chosen: day === i }" @click="day = i"><text>{{ label }}</text><text class="small">{{ dateLabel(i) }}</text></button></view><view class="form-two"><view><text class="field-label">开始时间</text><picker mode="time" :value="start" @change="start = $event.detail.value"><view class="picker-field">{{ start }} <wd-icon name="arrow-down" /></view></picker></view><view><text class="field-label">结束时间</text><picker mode="time" :value="end" @change="end = $event.detail.value"><view class="picker-field">{{ end }} <wd-icon name="arrow-down" /></view></picker></view></view><text class="field-label">{{ mode === 'venue' ? '选择示例场地' : '约球地点' }}</text><picker v-if="mode === 'venue'" :range="clubs.map(c => c.name)" :value="club" @change="club = Number($event.detail.value)"><view class="picker-field"><wd-icon name="location" /> {{ clubs[club].name }} <wd-icon name="arrow-down" /></view></picker><view v-else class="picker-field muted">地点待协商，不关联预约订单</view><text class="field-label">NTRP 球技等级</text><view class="choices"><button v-for="l in ['2.0','2.5','3.0','3.5','4.0']" :key="l" :class="{ chosen: level === l }" @click="level = l">{{ l }}</button></view><view class="summary-row"><text class="strong">总人数（包含你）</text><wd-input-number v-model="players" :min="2" :max="16" /></view><text class="field-label">人均费用（元） <text class="required">*</text></text><wd-input v-model="price" type="digit" placeholder="填写金额，免费填 0" /><text v-if="error" class="error-text" role="alert">{{ error }}</text><text v-if="done" class="feedback">发布成功，已加入约球广场（模拟）</text><view class="publish-action"><wd-button v-if="!done" block @click="publish">发布约球</wd-button><wd-button v-else block @click="go('home')">去广场看看</wd-button></view><text class="end-note">仅创建演示活动，不会通知真实用户</text></view></AppShell>
</template>
