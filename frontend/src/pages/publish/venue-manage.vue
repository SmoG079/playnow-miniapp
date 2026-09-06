<script setup lang="ts">
import { reactive, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, uploadFile } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  clubId = ref(0),
  id = ref(0),
  loading = ref(false),
  form = reactive<any>({
    name: "",
    sport_type: "tennis",
    price_per_hour: "",
    max_capacity: 4,
    cover_image: "",
    sort_order: 0,
    price_rules: [],
  });
onLoad(async (q) => {
  clubId.value = Number(q?.club_id);
  id.value = Number(q?.venue_id || 0);
  if (!s.requireLogin()) return;
  if (id.value) {
    const vs: any[] = await request(`/clubs/${clubId.value}/venues`);
    Object.assign(form, vs.find((v) => v.id === id.value) || {});
  }
});
function image() {
  uni.chooseImage({
    count: 1,
    sizeType: ["compressed"],
    success: (r) => (form.cover_image = r.tempFilePaths[0]),
  });
}
async function save() {
  if (!form.name || !(Number(form.price_per_hour) > 0))
    return uni.showToast({ title: "请填写名称和有效价格", icon: "none" });
  loading.value = true;
  try {
    if (form.cover_image && !/^https?:/.test(form.cover_image))
      form.cover_image = (await uploadFile(form.cover_image)).url;
    await request(
      id.value
        ? `/venues/${id.value}/with-club/${clubId.value}`
        : `/venues/with-club/${clubId.value}`,
      {
        method: id.value ? "PUT" : "POST",
        data: {
          ...form,
          price_per_hour: Number(form.price_per_hour),
          max_capacity: Number(form.max_capacity),
        },
      },
    );
    uni.showToast({ title: "保存成功", icon: "success" });
    setTimeout(() => uni.navigateBack(), 600);
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back :title="id ? '编辑场地' : '新增场地'"
    ><view class="content publish-content"
      ><text class="field-label">场地名称 *</text
      ><wd-input v-model="form.name" placeholder="例如 1 号室外硬地" /><text
        class="field-label"
        >每小时价格 *</text
      ><wd-input v-model="form.price_per_hour" type="digit" /><text
        class="field-label"
        >最大容量</text
      ><wd-input-number v-model="form.max_capacity" :min="1" :max="30" /><text
        class="field-label"
        >封面图</text
      ><view class="image-grid"
        ><Photo
          v-if="form.cover_image"
          width="100px"
          height="100px"
          :src="form.cover_image" /><button class="upload-box" @click="image">
          <wd-icon name="plus" /></button></view
      ><view class="publish-action"
        ><wd-button block :loading="loading" @click="save"
          >保存场地</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
