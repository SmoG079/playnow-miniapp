<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { request } from "../services/api";
import { useSession } from "../stores/session";

/**
 * Club block for an activity: tapping the row opens the club, the button joins
 * it directly without leaving the activity page.
 */
const props = defineProps<{
  clubId: number;
  name?: string | null;
  city?: string | null;
  logo?: string | null;
  ownerName?: string | null;
}>();
const session = useSession();
const joined = ref(false);
const isOwner = ref(false);
const memberCount = ref(0);
const busy = ref(false);

const subtitle = computed(() =>
  [props.city, memberCount.value ? `${memberCount.value} 位球友` : ""].filter(Boolean).join(" · "),
);

async function load() {
  if (!props.clubId) return;
  try {
    const community = await request<{ joined: boolean; owner: boolean; count: number }>(
      `/clubs/${props.clubId}/community`,
    );
    joined.value = !!community.joined;
    isOwner.value = !!community.owner;
    memberCount.value = community.count || 0;
  } catch {
    // Public viewers may not have a session; the card still renders.
  }
}

watch(() => props.clubId, load, { immediate: true });

async function toggle() {
  if (busy.value || isOwner.value) return;
  if (!session.requireLogin(`/pages/common/club-detail?id=${props.clubId}`)) return;
  busy.value = true;
  try {
    await request(`/clubs/${props.clubId}/community`, {
      method: joined.value ? "DELETE" : "POST",
    });
    uni.showToast({ title: joined.value ? "已退出俱乐部" : "已加入俱乐部", icon: "none" });
    await load();
  } catch (e: any) {
    uni.showToast({ title: e.message || "操作失败", icon: "none" });
  } finally {
    busy.value = false;
  }
}

function open() {
  uni.navigateTo({ url: `/pages/common/club-detail?id=${props.clubId}` });
}
</script>

<template>
  <view class="club-row">
    <view class="club-main" role="button" :aria-label="'查看俱乐部 ' + (name || '')" @click="open">
      <Photo :src="logo || undefined" width="52px" height="52px" fallback="/static/tennis.jpg" />
      <view class="club-copy">
        <text class="club-name">{{ name }}</text>
        <text v-if="subtitle" class="club-meta">{{ subtitle }}</text>
        <text v-if="ownerName" class="club-meta">主办人 {{ ownerName }}</text>
      </view>
      <wd-icon name="arrow-right" size="16px" color="var(--playnow-muted)" />
    </view>
    <wd-button
      v-if="!isOwner"
      size="small"
      :variant="joined ? 'plain' : 'base'"
      :loading="busy"
      @click.stop="toggle"
      >{{ joined ? "已加入" : "加入" }}</wd-button
    >
  </view>
</template>

<style scoped>
.club-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--playnow-card-border);
  border-radius: var(--playnow-card-radius);
  background: var(--playnow-surface);
}
.club-main {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 12px;
}
.club-copy {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}
.club-name {
  font-size: 16px;
  line-height: 22px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.club-meta {
  font-size: 12px;
  line-height: 18px;
  color: var(--playnow-muted);
}
</style>
