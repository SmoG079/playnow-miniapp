<script setup lang="ts">
import TournamentBracket from "./TournamentBracket.vue";
import { formatNames, type TournamentConfig, type Registration } from "../services/tournaments";
import type { SchedulePreview } from "../services/tournament-preview";
defineProps<{ preview: SchedulePreview; config: TournamentConfig; registrations?: Registration[]; myUserId?: number }>();
</script>
<template>
  <view class="preview-content"
    ><text class="preview-title">赛程预览</text
    ><text class="muted">{{ formatNames[config.format] }}</text>
    <text class="explanation">{{
      config.format === "knockout"
        ? "每轮捉对对局，胜者晋级，逐轮决出冠军。"
        : config.format === "round_robin"
          ? "同组队伍互相交手，按积分确定组内排名。"
          : "先进行小组循环赛，再由晋级队伍抽签进入淘汰阶段。"
    }}</text>
    <view class="statistics"
      ><view
        ><text>{{ preview.total_matches }}</text
        ><text>总场数</text></view
      ><view
        ><text>{{ preview.rounds }}</text
        ><text>轮次</text></view
      ><view
        ><text>≈{{ preview.estimated_minutes }}分钟</text
        ><text>预计时长</text></view
      ></view
    >
    <text class="muted">{{ preview.note }}</text
    ><text v-if="preview.overflows" class="warning"
      >预计超出赛事结束时间，请调整时长、场地或时间。</text
    ><text class="court-badge">{{ config.courts.join("、") }}</text>
    <TournamentBracket
      :teams="preview.teams"
      :matches="preview.matches"
      :registrations="registrations"
      :my-user-id="myUserId"
      all-groups
    />
    <template v-if="preview.knockout_preview"
      ><text class="preview-title">晋级淘汰阶段</text
      ><TournamentBracket
        :teams="preview.knockout_preview.teams"
        :matches="preview.knockout_preview.matches"
        all-groups
    /></template>
  </view>
</template>
<style scoped>
.preview-content {
  padding: 28px 16px 40px;
}
.preview-title {
  display: block;
  font-size: 24px;
  font-weight: 700;
}
.muted {
  display: block;
  color: #999;
  font-size: 12px;
  margin: 12px 0;
}
.explanation {
  display: block;
  line-height: 1.7;
  padding-left: 12px;
  border-left: 4px solid #d3fa45;
  margin: 20px 0;
}
.statistics {
  display: flex;
  gap: 8px;
  margin: 20px 0;
}
.statistics view {
  flex: 1;
  background: #f5f5f3;
  border-radius: var(--playnow-card-radius);
  border: 1px solid var(--playnow-card-border);
  text-align: center;
  padding: 16px 4px;
}
.statistics text {
  display: block;
  font-size: 20px;
  font-weight: 700;
}
.statistics text + text {
  margin-top: 8px;
  font-size: 12px;
  color: #999;
}
.court-badge {
  display: inline-block;
  background: #151515;
  color: #d3fa45;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.warning {
  display: block;
  color: #bd6d1a;
  margin: 12px 0;
  font-size: 12px;
}
</style>
