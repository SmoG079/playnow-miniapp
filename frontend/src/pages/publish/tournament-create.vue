<script setup lang="ts">
import { reactive, ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { listAll, request, uploadFile } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  clubs = ref<any[]>([]),
  index = ref(0),
  loading = ref(false),
  image = ref(""),
  linked = ref<any>(null),
  form = reactive<any>({
    title: "",
    sport_type: "网球",
    date: "",
    start: "09:00",
    end: "17:00",
    entry_fee: "0",
    max_participants: 16,
    description: "",
    prize: "",
  });
onLoad(async () => {
  if (!s.requireLogin()) return;
  await s.fetchUser();
  const ids = s.user?.managed_club_ids || [];
  clubs.value = (await listAll<any>("/clubs")).filter((c) =>
    ids.includes(c.id),
  );
  const d = new Date(Date.now() + 86400000);
  form.date = d.toISOString().slice(0, 10);
});
onShow(() => {
  const x = uni.getStorageSync("booking_return");
  if (x) {
    linked.value = x;
    form.date = x.slot_date;
    form.start = String(x.slot_start).slice(0, 5);
    form.end = String(x.slot_end).slice(0, 5);
    uni.removeStorageSync("booking_return");
  }
});
function pick() {
  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    success: (r) => (image.value = r.tempFilePaths[0]),
  });
}
async function save() {
  if (
    !form.title.trim() ||
    !form.date ||
    form.end <= form.start ||
    !clubs.value[index.value]
  )
    return uni.showToast({ title: "请检查名称、俱乐部和时间", icon: "none" });
  loading.value = true;
  try {
    const cover = image.value
      ? /^https?:/.test(image.value)
        ? image.value
        : (await uploadFile(image.value)).url
      : null;
    const t: any = await request("/tournaments", {
      method: "POST",
      data: {
        club_id: clubs.value[index.value].id,
        title: form.title,
        sport_type: form.sport_type,
        start_time: new Date(
          `${form.date}T${form.start}:00+08:00`,
        ).toISOString(),
        end_time: new Date(`${form.date}T${form.end}:00+08:00`).toISOString(),
        entry_fee: Number(form.entry_fee || 0),
        max_participants: Number(form.max_participants),
        description: form.description,
        prize: form.prize,
        venue_id: linked.value?.venue_id || null,
        lock_venue: !!linked.value,
        cover_image: cover,
      },
    });
    uni.redirectTo({ url: `/pages/common/tournament-detail?id=${t.id}` });
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back title="创建赛事"
    ><view class="content publish-content"
      ><text class="field-label">主办俱乐部</text
      ><picker
        :range="clubs.map((c) => c.name)"
        :value="index"
        @change="index = Number($event.detail.value)"
        ><view class="picker-field">{{
          clubs[index]?.name || "请选择"
        }}</view></picker
      ><text class="field-label">赛事名称 *</text
      ><wd-input v-model="form.title" /><text class="field-label">比赛日期</text
      ><picker
        mode="date"
        :value="form.date"
        @change="form.date = $event.detail.value"
        ><view class="picker-field">{{ form.date }}</view></picker
      ><view class="form-two"
        ><picker
          mode="time"
          :value="form.start"
          @change="form.start = $event.detail.value"
          ><view class="picker-field">{{ form.start }}</view></picker
        ><picker
          mode="time"
          :value="form.end"
          @change="form.end = $event.detail.value"
          ><view class="picker-field">{{ form.end }}</view></picker
        ></view
      ><wd-button
        block
        variant="plain"
        @click="
          uni.navigateTo({
            url:
              '/pages/booking/venue-detail?id=' +
              clubs[index]?.id +
              '&return_mode=tournament',
          })
        "
        >{{ linked ? "已关联场地，重新选择" : "预订并锁定比赛场地" }}</wd-button
      ><text class="field-label">报名费</text
      ><wd-input v-model="form.entry_fee" type="digit" /><text
        class="field-label"
        >人数上限</text
      ><wd-input-number v-model="form.max_participants" :min="1" /><text
        class="field-label"
        >赛事介绍</text
      ><wd-textarea v-model="form.description" /><text class="field-label"
        >奖项</text
      ><wd-input v-model="form.prize" /><button
        class="upload-box"
        @click="pick"
      >
        <wd-icon name="image" /> 封面图</button
      ><Photo v-if="image" width="100%" height="160px" :src="image" /><view
        class="publish-action"
        ><wd-button block :loading="loading" @click="save"
          >创建赛事</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
