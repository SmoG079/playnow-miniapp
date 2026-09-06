<script setup lang="ts">
import { tab } from '../data/fixtures'
defineProps<{ active?: string; back?: boolean; title?: string }>()
const nav = [ { key: 'home', name: '首页', icon: 'home' }, { key: 'clubs', name: '订场', icon: 'location' }, { key: 'publish', name: '发布', icon: 'plus' }, { key: 'chat', name: '消息', icon: 'message' }, { key: 'profile', name: '我的', icon: 'user' } ] as const
function backPage() { const pages = getCurrentPages(); if (pages.length > 1) uni.navigateBack(); else tab('home') }
</script>
<template>
  <wd-config-provider>
    <view class="app-shell">
      <view class="prototype-ribbon"><text>PLAYNOW LAB</text><text>交互原型 · 示例数据</text></view>
      <view v-if="back" class="topbar"><button class="icon-button" aria-label="返回" @click="backPage"><wd-icon name="arrow-left" size="22px" /></button><text class="topbar-title">{{ title }}</text><view class="topbar-spacer" /></view>
      <slot />
      <view v-if="active" class="bottom-nav">
        <button v-for="item in nav" :key="item.key" :class="['nav-item', { active: active === item.key, 'nav-publish': item.key === 'publish' }]" :aria-label="item.name" @click="tab(item.key)">
          <view class="nav-symbol"><wd-icon :name="item.icon" size="23px" /></view><text>{{ item.name }}</text>
        </button>
      </view>
    </view>
  </wd-config-provider>
</template>
