<script setup lang="ts">
import { reactive, ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { listAll, request, uploadFile } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  loading = ref(false),
  mode = ref("free"),
  clubs = ref<any[]>([]),
  clubIndex = ref(-1),
  images = ref<string[]>([]);
const today = () => new Date().toISOString().slice(0, 10);
const form = reactive<any>({
  title: "",
  preferred_date: today(),
  preferred_start: "19:00",
  preferred_end: "21:00",
  players_needed: 1,
  price: "0",
  level_required: "",
  description: "",
  notes: "",
  approval_required: false,
  venue_id: null,
  booking_id: null,
});
onShow(async () => {
  if (!s.requireLogin("/pages/publish/post-create")) return;
  await s.fetchUser().catch(() => {});
  const ids = s.user?.managed_club_ids || [];
  if (ids.length)
    clubs.value = (await listAll<any>("/clubs")).filter((c) =>
      ids.includes(c.id),
    );
  const linked = uni.getStorageSync("booking_return");
  if (linked) {
    Object.assign(form, {
      venue_id: linked.venue_id,
      booking_id: linked.booking_id,
      preferred_date: linked.slot_date,
      preferred_start: String(linked.slot_start).slice(0, 5),
      preferred_end: String(linked.slot_end).slice(0, 5),
    });
    uni.removeStorageSync("booking_return");
  }
});
function pickImages() {
  uni.chooseImage({
    count: 6 - images.value.length,
    sizeType: ["compressed"],
    success: (r) => images.value.push(...r.tempFilePaths),
  });
}
async function submit() {
  if (loading.value) return;
  if (!form.title.trim())
    return uni.showToast({ title: "请输入标题", icon: "none" });
  if (!form.preferred_date || !form.preferred_start || !form.preferred_end)
    return uni.showToast({ title: "请选择日期和时间", icon: "none" });
  if (form.preferred_end <= form.preferred_start)
    return uni.showToast({ title: "结束时间必须晚于开始时间", icon: "none" });
  if (
    !Number.isInteger(Number(form.players_needed)) ||
    Number(form.players_needed) < 1
  )
    return uni.showToast({ title: "人数至少为 1", icon: "none" });
  if (Number(form.price) < 0 || !Number.isFinite(Number(form.price)))
    return uni.showToast({ title: "请填写有效费用", icon: "none" });
  if (mode.value === "venue" && (clubIndex.value < 0 || !form.booking_id))
    return uni.showToast({ title: "请选择俱乐部并完成订场", icon: "none" });
  loading.value = true;
  try {
    const urls = [];
    for (const path of images.value)
      urls.push(path.startsWith("http") ? path : (await uploadFile(path)).url);
    await request("/posts", {
      method: "POST",
      data: {
        ...form,
        club_id:
          mode.value === "venue" ? clubs.value[clubIndex.value].id : null,
        price: Number(form.price),
        players_needed: Number(form.players_needed),
        level_required: form.level_required || null,
        images: urls.length ? urls : null,
      },
    });
    uni.showToast({ title: "发布成功", icon: "success" });
    setTimeout(() => uni.switchTab({ url: "/pages/home/index" }), 800);
  } catch (e: any) {
    uni.showToast({ title: e.message || "发布失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
function chooseClub(e: any) {
  clubIndex.value = Number(e.detail.value);
  form.booking_id = null;
  form.venue_id = null;
}
function goBook() {
  if (clubIndex.value < 0)
    return uni.showToast({ title: "请先选择俱乐部", icon: "none" });
  uni.navigateTo({
    url: `/pages/booking/venue-detail?id=${clubs.value[clubIndex.value].id}&return_mode=post`,
  });
}
</script>
<template>
  <AppShell active="publish"
    ><view class="content publish-content"
      ><view class="page-heading"
        ><text class="eyebrow">MAKE THE NEXT GAME</text
        ><text class="page-title">好球局，由你发起</text></view
      ><view class="mode-switch"
        ><button :class="{ chosen: mode === 'free' }" @click="mode = 'free'">
          自由约球</button
        ><button :class="{ chosen: mode === 'venue' }" @click="mode = 'venue'">
          关联场地
        </button></view
      ><text class="field-label">标题 *</text
      ><wd-input
        v-model="form.title"
        placeholder="例如：周五下班，一起打双打"
        :maxlength="40"
        clearable
      /><template v-if="mode === 'venue'"
        ><text class="field-label">俱乐部</text
        ><picker
          :range="clubs.map((c) => c.name)"
          :value="clubIndex"
          @change="chooseClub"
          ><view class="picker-field"
            >{{ clubIndex < 0 ? "请选择" : clubs[clubIndex].name
            }}<wd-icon name="arrow-down" /></view></picker
        ><wd-button block variant="plain" @click="goBook">{{
          form.booking_id ? "已关联预约，重新选择" : "去选择并预订场地"
        }}</wd-button></template
      ><text class="field-label">日期</text
      ><picker
        mode="date"
        :value="form.preferred_date"
        @change="form.preferred_date = $event.detail.value"
        ><view class="picker-field">{{ form.preferred_date }}</view></picker
      ><view class="form-two"
        ><view
          ><text class="field-label">开始</text
          ><picker
            mode="time"
            :value="form.preferred_start"
            @change="form.preferred_start = $event.detail.value"
            ><view class="picker-field">{{
              form.preferred_start
            }}</view></picker
          ></view
        ><view
          ><text class="field-label">结束</text
          ><picker
            mode="time"
            :value="form.preferred_end"
            @change="form.preferred_end = $event.detail.value"
            ><view class="picker-field">{{ form.preferred_end }}</view></picker
          ></view
        ></view
      ><text class="field-label">NTRP 要求</text
      ><wd-input
        v-model="form.level_required"
        placeholder="不限，例如 2.5-3.5"
      /><text class="field-label">还需要几人</text
      ><wd-input-number v-model="form.players_needed" :min="1" :max="30" /><text
        class="field-label"
        >人均费用（元）</text
      ><wd-input v-model="form.price" type="digit" /><text class="field-label"
        >活动说明</text
      ><wd-textarea
        v-model="form.description"
        show-word-limit
        :maxlength="1000"
      /><text class="field-label">活动图片</text
      ><view class="image-grid"
        ><wd-img
          v-for="(img, i) in images"
          :key="img"
          width="72px"
          height="72px"
          :src="img"
          @click="images.splice(i, 1)" /><button
          class="upload-box"
          @click="pickImages"
        >
          <wd-icon name="plus" /></button></view
      ><wd-cell title="报名需要审核"
        ><wd-switch v-model="form.approval_required" /></wd-cell
      ><view class="publish-action"
        ><wd-button block :loading="loading" @click="submit"
          >发布约球</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
