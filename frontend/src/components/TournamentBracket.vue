<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  teamName,
  localTime,
  type Team,
  type Match,
  type Registration,
} from "../services/tournaments";
import {
  bracketLayout,
  personalDraw,
  roundLabel,
} from "../services/tournament-preview";
const props = withDefaults(
  defineProps<{
    teams: Team[];
    matches: Match[];
    registrations?: Registration[];
    myUserId?: number;
    allGroups?: boolean;
  }>(),
  { registrations: () => [], allGroups: false },
);
const group = ref(1);
const groups = computed(() =>
  [...new Set(props.matches.map((m) => m.group_no))].sort((a, b) => a - b),
);
const mineInfo = computed(() =>
  personalDraw(props.teams, props.matches, props.myUserId),
);
watch(
  [groups, () => mineInfo.value?.team.group_no],
  () => {
    group.value = mineInfo.value?.team.group_no || groups.value[0] || 1;
  },
  { immediate: true },
);
const displayed = computed(() =>
  props.allGroups ? groups.value : [group.value],
);
const layouts = computed(() =>
  displayed.value.map((g) => ({
    group: g,
    ...bracketLayout(props.matches, g),
  })),
);
function name(id?: number | null) {
  return teamName(props.teams, id, props.registrations);
}
function mine(id?: number | null) {
  return props.teams
    .find((t) => t.id === id)
    ?.user_ids?.includes(props.myUserId || 0);
}
</script>
<template>
  <view class="bracket">
    <view v-if="mineInfo" class="my-position"
      ><text
        >我的签位：第 {{ mineInfo.team.group_no }} 组 ·
        {{ mineInfo.half }}</text
      ><wd-button
        size="small"
        variant="plain"
        @click="group = mineInfo.team.group_no"
        >定位我的分组</wd-button
      ></view
    >
    <view v-if="groups.length > 1 && !allGroups" class="group-picker"
      ><wd-button
        v-for="g in groups"
        :key="g"
        size="small"
        :variant="g === group ? 'base' : 'plain'"
        @click="group = g"
        >第 {{ g }} 组</wd-button
      ></view
    >
    <text v-if="!matches.length" class="muted"
      >待管理员抽签，签位将在正式发布后显示</text
    >
    <view v-for="layout in layouts" :key="layout.group" class="group-section">
      <text v-if="allGroups" class="group-badge">第 {{ layout.group }} 组</text>
      <scroll-view scroll-x class="tree-scroll">
        <view class="round-labels" :style="{ width: layout.width + 'px' }"
          ><text v-for="r in layout.rounds" :key="r" class="round-title">{{
            roundLabel(
              matches,
              layout.nodes.find(
                (n) => n.match.round_no === r && n.match.kind !== "third_place",
              )!.match,
            )
          }}</text></view
        >
        <view
          class="tree"
          :style="{ width: layout.width + 'px', height: layout.height + 'px' }"
        >
          <view v-for="edge in layout.edges" :key="edge.key" class="connector">
            <view
              class="line horizontal"
              :style="{
                left: edge.x + 'px',
                top: edge.from + 'px',
                width: '25px',
              }"
            />
            <view
              class="line vertical"
              :style="{
                left: edge.x + 25 + 'px',
                top: Math.min(edge.from, edge.to) + 'px',
                height: Math.abs(edge.to - edge.from) + 'px',
              }"
            />
            <view
              class="line horizontal"
              :style="{
                left: edge.x + 25 + 'px',
                top: edge.to + 'px',
                width: edge.targetX - edge.x - 25 + 'px',
              }"
            />
          </view>
          <view
            v-for="node in layout.nodes"
            :key="node.match.key"
            class="match-card"
            :class="{
              mine: mine(node.match.team_a_id) || mine(node.match.team_b_id),
            }"
            :style="{ left: node.x + 'px', top: node.y + 'px' }"
          >
            <text class="match-label">{{
              node.match.kind === "third_place"
                ? "季军赛"
                : node.match.id
                  ? "场次 #" + node.match.id
                  : "对阵 " + (node.match.position + 1)
            }}</text>
            <view
              class="entrant"
              :class="{
                winner:
                  node.match.winner_id &&
                  node.match.winner_id === node.match.team_a_id,
              }"
              >{{ name(node.match.team_a_id)
              }}<text v-if="!node.match.team_a_id" class="source">{{
                node.match.source_a
                  ? " · 前置" +
                    (node.match.source_outcome === "loser" ? "负者" : "胜者")
                  : " · 轮空"
              }}</text></view
            >
            <view
              class="entrant"
              :class="{
                winner:
                  node.match.winner_id &&
                  node.match.winner_id === node.match.team_b_id,
              }"
              >{{ name(node.match.team_b_id)
              }}<text v-if="!node.match.team_b_id" class="source">{{
                node.match.source_b
                  ? " · 前置" +
                    (node.match.source_outcome === "loser" ? "负者" : "胜者")
                  : " · 轮空"
              }}</text></view
            >
            <text class="match-footer"
              >{{
                node.match.status === "bye"
                  ? "轮空晋级"
                  : node.match.score || "待比赛"
              }}{{ node.match.is_draw ? " · 平局" : ""
              }}{{ node.match.walkover ? " · 弃权" : "" }}</text
            >
            <text v-if="node.match.court || node.match.scheduled_at" class="match-time">{{ node.match.court || "待排场" }} · {{ localTime(node.match.scheduled_at) }}</text>
          </view>
        </view>
      </scroll-view>
    </view>
  </view>
</template>
<style scoped>
.bracket {
  width: 100%;
}
.group-picker,
.my-position {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
}
.my-position {
  padding: 12px;
  background: #eff6e7;
  border-radius: 10px;
  font-size: 13px;
}
.group-section {
  padding: 20px 0;
  border-bottom: 1px solid #e6e6e6;
}
.group-badge {
  display: inline-block;
  padding: 6px 12px;
  margin-bottom: 20px;
  background: #d3fa45;
  border-radius: 6px;
  font-weight: 600;
}
.tree-scroll {
  width: 100%;
}
.round-labels {
  display: flex;
  padding-bottom: 20px;
}
.round-title {
  width: 210px;
  margin-right: 50px;
  flex-shrink: 0;
  text-align: center;
  color: #888;
  font-weight: 600;
}
.tree {
  position: relative;
}
.match-card {
  position: absolute;
  box-sizing: border-box;
  width: 210px;
  height: 132px;
  border: 1px solid #ddd;
  border-radius: 10px;
  background: white;
  overflow: hidden;
  z-index: 1;
}
.match-card.mine {
  border: 2px solid #78a72b;
  background: #fbfff4;
}
.match-label {
  display: block;
  padding: 5px 12px;
  color: #888;
  font-size: 11px;
}
.entrant {
  height: 38px;
  box-sizing: border-box;
  padding: 8px 12px;
  border-top: 1px solid #eee;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.winner {
  color: #4b7b15;
  font-weight: 700;
}
.source {
  font-size: 10px;
  color: #999;
}
.match-footer {
  display: block;
  font-size: 10px;
  color: #4b7b15;
  font-weight: 600;
  padding: 2px 12px;
}
.match-time { display: block; font-size: 9px; color: #888; padding: 0 12px; }
.line {
  position: absolute;
  background: #c7cebf;
}
.horizontal {
  height: 1px;
}
.vertical {
  width: 1px;
}
.muted {
  display: block;
  font-size: 12px;
  color: #888;
}
</style>
