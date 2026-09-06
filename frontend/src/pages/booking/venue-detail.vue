<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const clubId = ref(""),
  club = ref<any>(null),
  venues = ref<any[]>([]),
  rows = ref<any[]>([]),
  selected = ref<any[]>([]),
  date = ref(""),
  dates = ref<any[]>([]),
  loading = ref(false),
  returnMode = ref("");
const mins = (x: string) => {
  const p = x.split(":").map(Number);
  return p[0] * 60 + p[1];
};
const duration = computed(() =>
  selected.value.reduce((n, s) => n + mins(s.end_time) - mins(s.start_time), 0),
);
const total = computed(() =>
  selected.value.reduce((n, s) => n + Number(s.price || 0), 0).toFixed(2),
);
function init() {
  const d = new Date();
  dates.value = [0, 1, 2].map((i) => {
    const x = new Date(d);
    x.setDate(x.getDate() + i);
    return {
      label:
        i === 0
          ? "今天"
          : i === 1
            ? "明天"
            : `${x.getMonth() + 1}/${x.getDate()}`,
      value: `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`,
    };
  });
  date.value = dates.value[0].value;
}
async function load() {
  loading.value = true;
  selected.value = [];
  try {
    const [c, r] = await Promise.all([
      request<any>(`/clubs/${clubId.value}`),
      request<any>(`/clubs/${clubId.value}/venue-slots?date=${date.value}`),
    ]);
    club.value = c;
    venues.value = r.venues || c.venues || [];
    rows.value = r.rows || [];
  } catch (e: any) {
    uni.showToast({ title: e.message, icon: "none" });
  } finally {
    loading.value = false;
  }
}
onLoad((q) => {
  clubId.value = String(q?.id || q?.club_id || "");
  returnMode.value = String(q?.return_mode || "");
  init();
  load();
});
function selectedCell(c: any) {
  return selected.value.some((s) => s.slot_id === c.slot_id);
}
function choose(c: any) {
  if (c.status !== "available" || !c.slot_id) return;
  const idx = selected.value.findIndex((s) => s.slot_id === c.slot_id);
  if (idx >= 0) {
    selected.value.splice(idx);
    return;
  }
  if (selected.value.length) {
    const last = selected.value[selected.value.length - 1];
    if (
      last.venue_id !== c.venue_id ||
      mins(c.start_time) !== mins(last.end_time)
    )
      return uni.showToast({ title: "请选择同一场地的连续时段", icon: "none" });
  }
  selected.value.push(c);
}
function book() {
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
        ><wd-img
          width="100%"
          height="100%"
          :src="club.cover_image || '/static/court.jpg'"
          mode="aspectFill" /></view
      ><view class="content booking-content"
        ><text class="page-title compact">{{ club.name }}</text
        ><text class="muted"
          ><wd-icon name="location" /> {{ club.address }}</text
        ><view class="date-options section-head"
          ><button
            v-for="d in dates"
            :key="d.value"
            :class="{ chosen: date === d.value }"
            @click="
              date = d.value;
              load();
            "
          >
            <text>{{ d.label }}</text
            ><text class="small">{{ d.value.slice(5) }}</text>
          </button></view
        ><scroll-view scroll-x class="slot-scroll"
          ><view class="slot-table" :style="`--cols:${venues.length}`"
            ><view class="slot-header"
              ><text>时间</text
              ><text v-for="v in venues" :key="v.id">{{ v.name }}</text></view
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
        ><wd-loading v-if="loading" /><view class="booking-rules"
          ><text class="strong">预订须知</text
          ><text class="muted small"
            >请选择同一片场地的连续时段，至少 1 小时。</text
          ></view
        ></view
      ><view class="fixed-action"
        ><view
          ><text class="price large">¥{{ total }}</text
          ><text class="small muted">{{
            duration ? duration + " 分钟" : "请选择时段"
          }}</text></view
        ><wd-button :disabled="duration < 60" @click="book"
          >确认时段</wd-button
        ></view
      ></template
    ></AppShell
  >
</template>
