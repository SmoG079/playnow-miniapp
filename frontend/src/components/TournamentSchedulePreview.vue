<script setup lang="ts">
import TournamentBracket from "./TournamentBracket.vue";
import { formatNames, type TournamentConfig, type Registration } from "../services/tournaments";
import type { SchedulePreview } from "../services/tournament-preview";
defineProps<{ preview: SchedulePreview; config: TournamentConfig; registrations?: Registration[]; myUserId?: string }>();
</script>
<template>
  <view class="preview-content"
    ><text class="preview-title">赛程预览</text
    ><text class="preview-format">{{ formatNames[config.format] }}</text>
    <text class="explanation">{{
      config.format === "knockout"
        ? "每轮捉对对局，胜者晋级，逐轮决出冠军。"
        : config.format === "round_robin"
          ? "同组队伍互相交手，按积分确定组内排名。"
          : "先进行小组循环赛，再由晋级队伍抽签进入淘汰阶段。"
    }}</text>
    <view class="statistics"
      ><view class="stat-card"
        ><text class="stat-value">{{ preview.total_matches }}</text
        ><text class="stat-label">总场数</text></view
      ><view class="stat-card"
        ><text class="stat-value">{{ preview.rounds }}</text
        ><text class="stat-label">轮次</text></view
      ><view class="stat-card"
        ><text class="stat-value stat-duration">≈{{ preview.estimated_minutes }}分钟</text
        ><text class="stat-label">预计时长</text></view
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
  --playnow-card-border: #dce8df;
  --playnow-card-radius: 14px;
  padding: 28px 16px 40px;
  background: #f5f8f6;
  color: #183326;
}
.preview-title {
  display: block;
  padding-right: 28px;
  font-size: 22px;
  line-height: 30px;
  font-weight: 700;
}
.preview-format {
  display: inline-block;
  padding: 4px 9px;
  margin-top: 10px;
  border: 1px solid #dce8df;
  border-radius: 8px;
  background: #edf6ef;
  color: #00633c;
  font-size: 12px;
  line-height: 18px;
}
.muted {
  display: block;
  color: #718579;
  font-size: 12px;
  line-height: 20px;
  margin: 12px 0;
}
.explanation {
  display: block;
  line-height: 1.7;
  padding: 12px 14px;
  border: 1px solid #dce8df;
  border-left: 3px solid #147553;
  border-radius: 10px;
  background: #fff;
  color: #3c5b49;
  font-size: 14px;
  margin: 16px 0;
}
.statistics {
  display: flex;
  gap: 8px;
  margin: 16px 0;
}
.stat-card {
  flex: 1;
  min-width: 0;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #dce8df;
  text-align: center;
  padding: 16px 4px;
}
.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #00633c;
  line-height: 28px;
  overflow-wrap: anywhere;
}
.stat-duration { font-size: 16px; }
.stat-label {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  color: #718579;
  line-height: 18px;
}
.court-badge {
  display: inline-block;
  border: 1px solid #cfe3d5;
  background: #e7f2eb;
  color: #00633c;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
}
.warning {
  display: block;
  color: #bd6d1a;
  background: #fff8ee;
  border: 1px solid #efdbc0;
  border-radius: 10px;
  padding: 10px 12px;
  line-height: 20px;
  margin: 12px 0;
  font-size: 12px;
}
</style>
