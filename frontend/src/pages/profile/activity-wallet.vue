<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
declare const wx: any;
const session = useSession(), data = ref<any>(null), busy = ref(false), error = ref("");
const start = ref(""), end = ref(""), clubId = ref(0);
const requestKeys = new Map<string, string>();
const money = (cents: number) => (Number(cents || 0) / 100).toFixed(2);
const states: Record<string,string> = { NEW:"待提交", SUBMITTING:"正在核对", ACCEPTED:"已受理", PROCESSING:"处理中", WAIT_USER_CONFIRM:"待确认收款", TRANSFERING:"转账中", SUCCESS:"已到账", FAIL:"失败，金额已释放", CANCELLED:"已关闭，金额已释放", CANCELING:"撤销中" };
onLoad(q => { clubId.value = Number(q?.club_id || 0); });
async function load() {
  if (!session.requireLogin("/pages/profile/activity-wallet")) return;
  error.value = "";
  try {
    const params = [start.value && `start=${start.value}`, end.value && `end=${end.value}`, clubId.value && `club_id=${clubId.value}`].filter(Boolean).join("&");
    data.value = await request(`/activity-wallet?${params}`);
  } catch (e:any) { error.value = e.message || "加载失败，请重试"; }
}
onShow(load);
async function confirmReceipt(id: number) {
  let result: any = await request(`/activity-wallet/transfers/${id}/sync`, {method:"POST"});
  if (result.confirmation) {
    // #ifdef MP-WEIXIN
    if (!(wx as any).canIUse("requestMerchantTransfer")) throw new Error("请更新微信版本后确认收款");
    await new Promise<void>((resolve,reject) => (wx as any).requestMerchantTransfer({ ...result.confirmation, success: () => resolve(), fail: (e:any) => reject(new Error(e.errMsg?.includes("cancel") ? "已暂停，可在提现记录中继续确认" : "收款页面未能打开，请稍后重试")) }));
    result = await request(`/activity-wallet/transfers/${id}/sync`, {method:"POST"});
    // #endif
    // #ifndef MP-WEIXIN
    throw new Error("请在微信小程序内确认收款");
    // #endif
  }
  return result.state === "SUCCESS";
}
async function resume(id:number) {
  if (busy.value) return;
  busy.value = true;
  try { const paid = await confirmReceipt(id); uni.showToast({title: paid ? "已确认到账" : "正在处理，请稍后刷新",icon:"none"}); }
  catch (e:any) { uni.showToast({title:e.message,icon:"none"}); }
  finally { busy.value=false; await load(); }
}
async function submit(activity?:any) {
  if (busy.value || !data.value?.enabled) return;
  const selected = activity ? [activity] : data.value.activities.filter((x:any) => x.available_cents > 0);
  const ids = selected.map((x:any) => x.activity_id);
  if (!ids.length) return;
  const confirmation = await uni.showModal({title:selected.length > 1 ? "跨活动提现" : "活动提现",content:`提取所选 ${selected.length} 场活动的活动收入。单笔最高 ¥${money(data.value.maximum_cents)}，同时受单用户每日 ¥${money(data.value.daily_limit_cents)} 限额约束。申请后将展示本次实际金额与拆单明细。`});
  if (!confirmation.confirm) return;
  busy.value = true;
  const scope = ids.slice().sort().join(",");
  const key = requestKeys.get(scope) || `aw_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  requestKeys.set(scope,key);
  try {
    const result:any = await request("/activity-wallet/withdrawals",{method:"POST",data:{request_key:key,activity_ids:ids}});
    requestKeys.delete(scope);
    const accepted = await uni.showModal({title:"确认活动提现",content:`${selected.length} 场活动共 ¥${money(result.amount_cents)}，分为 ${result.bills.length} 笔：${result.bills.map((b:any)=>'¥'+money(b.amount_cents)).join('、')}。微信将逐笔请求确认，未确认的款项可稍后在提现记录中继续领取。`});
    if (accepted.confirm) {
      for (const bill of result.bills) {
        if (!await confirmReceipt(bill.id)) break;
      }
    }
  } catch(e:any) { uni.showToast({title:e.message || "申请失败，请重试",icon:"none"}); }
  finally { busy.value=false; await load(); }
}
</script>
<template>
  <AppShell back title="活动提现"><view class="content wallet">
    <text v-if="error" class="muted">{{ error }}</text><wd-button v-if="error" @click="load">重试</wd-button>
    <template v-if="data">
      <view class="wallet-hero"><text>当前账户可提现</text><text class="wallet-total">¥{{ money(data.available_cents) }}</text><text>已到账 ¥{{ money(data.paid_cents) }} · 处理中 ¥{{ money(data.pending_cents) }}</text><text v-if="data.debt_cents">待抵扣 ¥{{ money(data.debt_cents) }}，请联系平台核对退款</text></view>
      <view class="wallet-card"><text class="section-title">资金流水</text><view class="wallet-dates"><picker mode="date" :value="start" @change="start=$event.detail.value"><text>{{ start || '开始日期' }}</text></picker><text>至</text><picker mode="date" :value="end" @change="end=$event.detail.value"><text>{{ end || '结束日期' }}</text></picker><wd-button size="small" @click="load">查询</wd-button></view><text>活动收入 ¥{{ money(data.gross_cents) }} · 退款 ¥{{ money(data.refund_cents) }}</text><text>锁定中 ¥{{ money(data.locked_cents) }}</text><text>微信支付手续费{{ data.fee_verified ? '（按签约费率计算）' : '（预估）' }} ¥{{ money(data.fee_cents) }}</text><text>平台服务费 ¥0.00</text></view>
      <view class="wallet-card rules"><text class="section-title">提现规则</text><text>提现解锁：活动结束 24 小时后可提取活动收入，锁定期间显示“锁定中”。退款处理中或尚未确认的收入不能提现。</text><text>提现时间：全天可提交申请，实际处理受可用余额和转账额度限制。</text><text>微信支付手续费按 {{ (Number(data.fee_rate)*100).toFixed(2) }}% {{ data.fee_verified ? '计算' : '预估' }}，由组织者承担。平台服务费为 0，费用及预计到账金额以本页明细为准。</text><text>可提现额度：单笔 ¥{{ money(data.minimum_cents) }}–¥{{ money(data.maximum_cents) }}，单用户每日限额 ¥{{ money(data.daily_limit_cents) }}；超过额度的部分需之后申请。</text><text>到账说明：提交后需逐笔在微信确认收款，实际到账状态以微信处理结果为准。未及时确认的款项可能过期关闭，可在提现记录中查看进度。</text><text v-if="!data.enabled">{{ data.disabled_reason }}</text><text>日期及俱乐部筛选只影响活动列表；顶部余额为本人全部活动账户余额。</text></view>
      <wd-button block :disabled="busy || !data.enabled || data.available_cents < data.minimum_cents" :loading="busy" @click="submit()">提取当前列表活动收入</wd-button>
      <view v-for="activity in data.activities" :key="activity.kind+activity.activity_id" class="wallet-card"><text class="section-title">#{{ activity.activity_id }} {{ activity.title }}</text><text>{{ activity.date }} · {{ activity.count }} 笔收入</text><text>收入 ¥{{ money(activity.gross_cents) }} · 手续费 ¥{{ money(activity.fee_cents) }} · 可提现 ¥{{ money(Math.max(0,activity.available_cents)) }}</text><text v-if="activity.locked_cents">锁定中 ¥{{ money(activity.locked_cents) }}</text><wd-button size="small" :disabled="busy || !data.enabled || activity.available_cents < data.minimum_cents" @click="submit(activity)">提现本活动</wd-button></view>
      <text v-if="!data.activities.length" class="muted">当前范围暂无可提取的活动收入</text>
      <view class="wallet-card"><text class="section-title">提现记录</text><view v-for="bill in data.transfers" :key="bill.id" class="wallet-record"><text>¥{{ money(bill.amount_cents) }} · {{ states[bill.state] || '待核对' }}</text><wd-button v-if="!['SUCCESS','FAIL','CANCELLED'].includes(bill.state)" size="small" :disabled="busy" @click="resume(bill.id)">刷新／继续收款</wd-button></view><text v-if="!data.transfers.length" class="muted">暂无提现记录</text></view>
    </template><text v-else-if="!error">正在加载…</text>
  </view></AppShell>
</template>
<style scoped>.wallet{padding-bottom:40px}.wallet-hero{display:flex;flex-direction:column;gap:12px;background:#153f31;color:#fff;padding:24px;border-radius:22px}.wallet-total{font-size:40px;font-weight:700}.wallet-card{display:flex;flex-direction:column;gap:12px;padding:20px;background:white;border-radius:18px;margin:18px 0}.wallet-dates,.wallet-record{display:flex;align-items:center;justify-content:space-between;gap:10px}.wallet-dates{font-size:12px}.rules{font-size:13px;line-height:1.7;color:#64746c}.wallet-record{padding:12px 0;border-bottom:1px solid #eef2ef}</style>
