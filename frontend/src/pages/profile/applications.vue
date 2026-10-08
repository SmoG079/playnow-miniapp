<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShow, onReachBottom, onPullDownRefresh } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const session = useSession();
const scopes = [{ value: "todo", label: "待处理" }, { value: "done", label: "已处理" }, { value: "mine", label: "我的申请" }];
const scope = ref("todo"), kind = ref("all"), rows = ref<any[]>([]), page = ref(1), more = ref(true), loading = ref(false), failed = ref(false), processing = ref("");
const details = ref<Record<string, any>>({});
const kindNames: Record<string, string> = { club: "俱乐部创建", post: "约球报名", tournament: "比赛报名" };
const statusNames: Record<string, string> = { pending: "等待审核", approved: "已通过", rejected: "未通过" };
let loadVersion = 0;
const key = (row: any) => `${row.kind}:${row.application_id}`;
async function load(append = false) {
  if (append && (loading.value || !more.value)) return;
  const version = ++loadVersion;
  loading.value = true; failed.value = false;
  const next = append ? page.value + 1 : 1;
  try {
    const result = await request<PageResult<any>>(`/applications?scope=${scope.value}&kind=${kind.value}&page=${next}&page_size=20`);
    if (version !== loadVersion) return;
    rows.value = append ? [...rows.value, ...result.items] : result.items;
    page.value = next; more.value = rows.value.length < (result.total || 0);
  } catch (error: any) {
    if (version === loadVersion) { failed.value = true; uni.showToast({ title: error.message || "申请加载失败", icon: "none" }); }
  } finally { if (version === loadVersion) loading.value = false; }
}
function changeScope(value: string) { scope.value = value; rows.value = []; details.value = {}; void load(); }
function filter(e: any) { kind.value = ["all", "club", "post", "tournament"][Number(e.detail.value)]; rows.value = []; void load(); }
async function showDetails(row: any) {
  if (row.kind !== "club") return openPage(`/pages/common/${row.kind === "post" ? "post" : "tournament"}-detail?id=${row.target_id}`);
  if (details.value[key(row)]) { delete details.value[key(row)]; return; }
  try { details.value[key(row)] = await request(`/clubs/${row.target_id}`); }
  catch (error: any) { uni.showToast({ title: error.message || "资料加载失败", icon: "none" }); }
}
function review(row: any, approved: boolean) {
  if (processing.value) return;
  uni.showModal({
    title: approved ? "通过申请" : "拒绝申请", content: approved ? `确认通过${row.applicant || "球友"}的${kindNames[row.kind]}申请？` : "",
    editable: !approved, placeholderText: "请填写拒绝原因（必填）",
    success: async result => {
      if (!result.confirm || processing.value) return;
      const reason = approved ? "审核通过" : (result.content || "").trim();
      if (!reason) return uni.showToast({ title: "请填写拒绝原因", icon: "none" });
      processing.value = key(row);
      try {
        const path = row.kind === "club" ? `/applications/clubs/${row.application_id}/review` : `/applications/${row.kind}/${row.application_id}/review`;
        await request(path, { method: "POST", data: { approved, reason } });
        uni.showToast({ title: "已处理", icon: "success" });
        await session.fetchUser(); await load();
      } catch (error: any) { uni.showToast({ title: error.message || "处理失败，请重试", icon: "none" }); }
      finally { processing.value = ""; }
    },
  });
}
onLoad(q => { if (["post","tournament","club"].includes(String(q?.kind))) kind.value = String(q?.kind); });
onShow(async () => { if (!session.requireLogin("/pages/profile/applications")) return; await session.fetchUser().catch(() => {}); await load(); });
onReachBottom(() => load(true));
onPullDownRefresh(() => load().finally(() => uni.stopPullDownRefresh()));
</script>
<template>
  <AppShell back title="申请处理"><view class="content list-content">
    <view class="text-tabs"><button v-for="tab in scopes" :key="tab.value" :class="{selected:scope === tab.value}" @click="changeScope(tab.value)">{{ tab.label }}</button></view>
    <text class="muted small inbox-hint">{{ scope === 'mine' ? '查看自己的俱乐部申请进度与审核结果' : (session.isPlatformAdmin ? '俱乐部创建由系统管理员审核；报名由发起者审核' : '处理自己发起的约球和比赛报名申请') }}</text>
    <picker v-if="scope !== 'mine'" :range="['全部申请','俱乐部创建','约球报名','比赛报名']" @change="filter"><view class="picker-field">{{ kind === 'all' ? '全部申请' : kindNames[kind] }}<wd-icon name="arrow-down" size="14px" /></view></picker>
    <view v-for="row in rows" :key="key(row)" class="record-card application-card">
      <view class="row gap8"><Photo round width="40px" height="40px" :src="row.avatar_url" fallback="/static/tennis.jpg" /><view class="applicant"><text class="strong">{{ row.applicant || '球友' }}</text><text class="muted small">{{ kindNames[row.kind] }} · {{ row.city || '' }}</text></view><text class="tag" :class="{yellow:row.status === 'pending'}">{{ statusNames[row.status] || row.status }}</text></view>
      <text class="application-title">{{ row.title }}</text><text v-if="row.description" class="muted small">{{ row.description }}</text><text v-if="row.reason" class="review-reason">审核说明：{{ row.reason }}</text>
      <view v-if="details[key(row)]" class="application-details"><text class="muted small">{{ details[key(row)].description || '暂无介绍' }}</text><text class="muted small">联系电话：{{ details[key(row)].contact_phone }}</text><view class="detail-images"><Photo v-for="url in details[key(row)].images || []" :key="url" :src="url" width="80px" height="80px" /></view></view>
      <view class="row application-actions"><wd-button variant="text" size="small" @click="showDetails(row)">{{ row.kind === 'club' ? (details[key(row)] ? '收起资料' : '查看申请资料') : '查看活动' }}</wd-button><view v-if="row.can_review" class="row gap8"><wd-button size="small" variant="plain" type="danger" :disabled="!!processing" @click="review(row,false)">拒绝</wd-button><wd-button size="small" :loading="processing === key(row)" :disabled="!!processing" @click="review(row,true)">通过</wd-button></view></view>
    </view>
    <view v-if="failed" class="empty-state"><text class="muted">申请暂时加载失败</text><wd-button size="small" @click="load()">重试</wd-button></view>
    <wd-empty v-else-if="!loading && !rows.length" :tip="scope === 'todo' ? '暂无待处理申请' : '暂无申请记录'" />
    <text v-if="loading" class="muted inbox-hint">正在加载…</text>
  </view></AppShell>
</template>
<style scoped>
.inbox-hint{display:block;margin:16px 0;line-height:1.6}.application-card{margin-top:14px}.applicant{flex:1;min-width:0}.application-title{display:block;font-weight:600;margin:16px 0 8px}.application-actions{justify-content:space-between;margin-top:16px}.review-reason{display:block;background:#f4f7f5;border-radius:8px;padding:10px;margin-top:12px;font-size:13px;color:#647d70}.application-details{border-top:1px solid var(--playnow-card-border);padding-top:12px;margin-top:12px;display:flex;flex-direction:column;gap:10px}.detail-images{display:flex;flex-wrap:wrap;gap:8px}
</style>
