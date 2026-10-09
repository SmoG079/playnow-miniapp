<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { businessDate } from "../../utils/date";
import { bookingDuration, selectBookingCell } from "../../domain/booking";
const clubId = ref(""),
  club = ref<any>(null),
  venues = ref<any[]>([]),
  rows = ref<any[]>([]),
  selected = ref<any[]>([]),
  date = ref(""),
  dates = ref<any[]>([]),
  clubLoading = ref(false),
  clubFailed = ref(false),
  slotsFailed = ref(false),
  loading = ref(false),
  returnMode = ref("");
const duration = computed(() => bookingDuration(selected.value));
const total = computed(() =>
  selected.value.reduce((n, s) => n + Number(s.price || 0), 0).toFixed(2),
);
function init() {
  const now = Date.now();
  dates.value = [0, 1, 2].map((i) => {
    const value = businessDate(now + i * 86400000);
    return {
      label:
        i === 0
          ? "今天"
          : i === 1
            ? "明天"
            : `${Number(value.slice(5, 7))}/${Number(value.slice(8, 10))}`,
      value,
    };
  });
  date.value = dates.value[0].value;
}
let loadVersion = 0;
async function loadClub() {
  if (clubLoading.value) return;
  clubLoading.value = true;
  clubFailed.value = false;
  try {
    club.value = await request<any>(`/clubs/${clubId.value}`);
  } catch (e: any) {
    clubFailed.value = true;
  } finally {
    clubLoading.value = false;
  }
}
async function loadSlots() {
  const version = ++loadVersion;
  loading.value = true;
  slotsFailed.value = false;
  selected.value = [];
  rows.value = [];
  try {
    const r = await request<any>(`/clubs/${clubId.value}/venue-slots?date=${date.value}`);
    if (version !== loadVersion) return;
    venues.value = r.venues || [];
    rows.value = r.rows || [];
  } catch (e: any) {
    if (version === loadVersion) slotsFailed.value = true;
  } finally {
    if (version === loadVersion) loading.value = false;
  }
}
onLoad((q) => {
  clubId.value = String(q?.id || q?.club_id || "");
  returnMode.value = String(q?.return_mode || "");
  init();
  void loadClub();
  void loadSlots();
});
function retryClub() {
  void loadClub();
  void loadSlots();
}
function selectedCell(c: any) {
  return selected.value.some((s) => s.slot_id === c.slot_id);
}
function choose(c: any) {
  if (loading.value) return;
  const result = selectBookingCell(selected.value, c, rows.value.flatMap(row => row.cells));
  if (result.error) return uni.showToast({ title: result.error, icon: "none" });
  selected.value = result.slots;
}
function courtLocation(v: any) {
  if (v.latitude != null && v.longitude != null) uni.openLocation({ latitude: Number(v.latitude), longitude: Number(v.longitude), name: v.name, address: v.address || "" });
  else uni.showModal({ title: v.name, content: v.address || "球场位置尚未补充，请联系管理员", showCancel: false });
}
function book() {
  if (loading.value) return;
  if (duration.value < 60)
    return uni.showToast({ title: "请至少选择 1 小时", icon: "none" });
  const first = selected.value[0],
    last = selected.value[selected.value.length - 1],
    v = venues.value.find((x) => x.id === first.venue_id);
  uni.navigateTo({
    url: `/pages/booking/confirm?slot_ids=${selected.value.map((s) => s.slot_id).join(",")}&venue_id=${first.venue_id}&price=${total.value}&date=${date.value}&start=${first.start_time}&end=${last.end_time}&venue_name=${encodeURIComponent(v?.name || "")}${returnMode.value ? "&return_mode=" + returnMode.value : ""}`,
  });
}
</script>
<template>
  <AppShell back title="选择时段"
    ><template v-if="club"
      ><view class="detail-photo"
        ><Photo
          width="100%"
          height="100%"
          :src="club.cover_image"
          fallback="/static/court.jpg"
          mode="aspectFill" /></view
      ><view class="content booking-content"
        ><text class="page-title compact">{{ club.name }}</text
        ><text class="muted"
          >选择下方球场查看实际位置</text
        ><view class="date-options section-head"
          ><button
            v-for="d in dates"
            :key="d.value"
            :class="{ chosen: date === d.value }"
            @click="
              date = d.value;
              loadSlots();
            "
          >
            <text>{{ d.label }}</text
            ><text class="small">{{ d.value.slice(5) }}</text>
          </button></view
        ><view v-if="loading" class="page-loading"><wd-loading text="正在加载可订时段" /></view>
        <view v-else-if="slotsFailed" class="empty-state">
          <wd-icon name="info-circle" size="36px" color="#728178" />
          <text class="section-title">时段加载失败</text>
          <text class="muted small">请检查网络后重新加载</text>
          <wd-button size="small" variant="plain" @click="loadSlots">重新加载</wd-button>
        </view>
        <wd-empty v-else-if="!venues.length || !rows.length" tip="当天暂无可订时段" />
        <scroll-view v-else scroll-x class="slot-scroll"
          ><view class="slot-table" :style="`--cols:${venues.length}`"
            ><view class="slot-header"
              ><text>时间</text
              ><text v-for="v in venues" :key="v.id" @click="courtLocation(v)">{{ v.name }}<text class="small muted">{{ v.address || '位置待补充' }}</text></text></view
            ><view v-for="r in rows" :key="r.time_label" class="slot-row"
              ><text class="time-label">{{ r.time_label }}</text
              ><button
                v-for="c in r.cells"
                :key="c.slot_id || c.venue_id"
                :disabled="c.status !== 'available'"
                :class="[
                  'slot',
                  {
                    picked: selectedCell(c),
                    unavailable: c.status !== 'available',
                  },
                ]"
                @click="choose(c)"
              >
                {{
                  c.status === "available"
                    ? selectedCell(c)
                      ? "已选"
                      : "¥" + c.price
                    : c.status === "booked"
                      ? "已订"
                      : "—"
                }}
              </button></view
            ></view
          ></scroll-view
        ><view class="booking-rules"
          ><text class="strong">预订须知</text
          ><text class="muted small"
            >1 小时起订，首次点击自动选择后续连续时段；之后可按半小时追加。</text
          ></view
        ></view
      ><view class="fixed-action"
        ><view
          ><text class="price large">¥{{ total }}</text
          ><text class="small muted">{{
            duration ? duration + " 分钟" : "请选择时段"
          }}</text></view
        ><wd-button :disabled="loading || slotsFailed || duration < 60" @click="book"
          >确认时段</wd-button
        ></view
      ></template
    ><view v-else-if="clubFailed" class="content empty-state">
      <wd-icon name="info-circle" size="44px" color="#728178" />
      <text class="section-title">球场信息加载失败</text>
      <text class="muted">请检查网络后重新加载</text>
      <wd-button size="small" @click="retryClub">重新加载</wd-button>
    </view>
    <view v-else class="page-loading"><wd-loading text="正在加载球场信息" /></view>
    </AppShell
  >
</template>
