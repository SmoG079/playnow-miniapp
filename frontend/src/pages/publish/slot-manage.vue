<script setup lang="ts">
import { reactive, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
const clubId = ref(0),
  venues = ref<any[]>([]),
  index = ref(0),
  slots = ref<any[]>([]),
  loading = ref(false),
  intervals = [30, 60, 90, 120],
  intervalIndex = ref(1);
const fmt = (d: Date) => d.toISOString().slice(0, 10),
  form = reactive({
    date_from: fmt(new Date()),
    date_to: fmt(new Date(Date.now() + 7 * 86400000)),
    start_time: "08:00",
    end_time: "22:00",
  });
onLoad(async (q) => {
  clubId.value = Number(q?.club_id);
  venues.value = await request(`/clubs/${clubId.value}/venues`);
  const i = venues.value.findIndex((v) => v.id === Number(q?.venue_id));
  index.value = i < 0 ? 0 : i;
  load();
});
async function load() {
  if (!venues.value[index.value]) return;
  const groups: any[] = await request(
    `/venues/${venues.value[index.value].id}/slots?date_from=${form.date_from}&date_to=${form.date_to}`,
  );
  slots.value = groups.flatMap((g) =>
    (g.slots || []).map((s: any) => ({ ...s, date_label: g.date })),
  );
}
async function generate() {
  if (form.date_to < form.date_from || form.end_time <= form.start_time)
    return uni.showToast({ title: "请检查日期和时间范围", icon: "none" });
  loading.value = true;
  try {
    const r: any = await request(
      `/venues/${venues.value[index.value].id}/slots/batch?club_id=${clubId.value}`,
      {
        method: "POST",
        data: {
          ...form,
          start_time: form.start_time + ":00",
          end_time: form.end_time + ":00",
          interval_minutes: intervals[intervalIndex.value],
          price_rules: [],
        },
      },
    );
    uni.showToast({ title: `新增 ${r.created} 个时段`, icon: "success" });
    load();
  } finally {
    loading.value = false;
  }
}
async function toggle(x: any) {
  await request(
    `/venues/${venues.value[index.value].id}/slots/${x.id}/status`,
    {
      method: "PATCH",
      data: { status: x.status === "available" ? "maintenance" : "available" },
    },
  );
  load();
}
</script>
<template>
  <AppShell back title="时段管理"
    ><view class="content publish-content"
      ><text class="field-label">场地</text
      ><picker
        :range="venues.map((v) => v.name)"
        :value="index"
        @change="
          index = Number($event.detail.value);
          load();
        "
        ><view class="picker-field">{{ venues[index]?.name }}</view></picker
      ><text class="section-title section-head">批量生成</text
      ><view class="form-two"
        ><picker
          mode="date"
          :value="form.date_from"
          @change="form.date_from = $event.detail.value"
          ><view class="picker-field">{{ form.date_from }}</view></picker
        ><picker
          mode="date"
          :value="form.date_to"
          @change="form.date_to = $event.detail.value"
          ><view class="picker-field">{{ form.date_to }}</view></picker
        ></view
      ><view class="form-two"
        ><picker
          mode="time"
          :value="form.start_time"
          @change="form.start_time = $event.detail.value"
          ><view class="picker-field">{{ form.start_time }}</view></picker
        ><picker
          mode="time"
          :value="form.end_time"
          @change="form.end_time = $event.detail.value"
          ><view class="picker-field">{{ form.end_time }}</view></picker
        ></view
      ><picker
        :range="intervals.map((x) => x + ' 分钟')"
        :value="intervalIndex"
        @change="intervalIndex = Number($event.detail.value)"
        ><view class="picker-field"
          >{{ intervals[intervalIndex] }} 分钟</view
        ></picker
      ><wd-button block :loading="loading" @click="generate">生成时段</wd-button
      ><text class="section-title section-head">已有时段</text
      ><view v-for="x in slots" :key="x.id" class="record-card"
        ><view
          ><text class="strong"
            >{{ x.date_label }} {{ x.start_time }}–{{ x.end_time }}</text
          ><text class="muted small"
            >¥{{ x.price }} · {{ x.status }}</text
          ></view
        ><wd-switch
          :model-value="x.status === 'available'"
          :disabled="x.status === 'booked'"
          @change="toggle(x)" /></view
      ><wd-empty v-if="!slots.length" tip="该范围暂无时段" /></view
  ></AppShell>
</template>
