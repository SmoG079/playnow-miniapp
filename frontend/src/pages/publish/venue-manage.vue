<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import ActivityLocationSelect from "../../components/ActivityLocationSelect.vue";
import AppShell from "../../components/AppShell.vue";
import { chooseUploadedImages, uploadedImage } from "../../services/media";
import { request } from "../../services/api";
import { useDiscovery } from "../../stores/discovery";
import { useSession } from "../../stores/session";
const discovery = useDiscovery();
const s = useSession(),
  clubId = ref(0),
  id = ref(0),
  loading = ref(false),
  imageUploading = ref(false),
  locationSelecting = ref(false),
  form = reactive<any>({
    name: "",
    city: discovery.city, address: "", latitude: null, longitude: null,
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
  if (!id.value) { await discovery.ensureCity().catch(() => {}); form.city = discovery.city; }
  if (id.value) {
    const vs: any[] = await request(`/clubs/${clubId.value}/venues`);
    Object.assign(form, vs.find((v) => v.id === id.value) || {});
  }
});
watch(() => discovery.city, value => {
  if (!id.value && form.city !== value) {
    form.city = value; form.address = ""; form.latitude = null; form.longitude = null;
  }
}, { flush: "sync" });
async function image() {
  if (loading.value || imageUploading.value) return;
  imageUploading.value = true;
  try { await chooseUploadedImages(1, "court", url => { form.cover_image = url; }); }
  catch (error: any) { uni.showToast({ title: error.message || "图片上传失败，请重试", icon: "none" }); }
  finally { imageUploading.value = false; }
}
async function save() {
  if (locationSelecting.value || loading.value || imageUploading.value) return;
  if (!form.city || !form.address.trim() || form.latitude == null || form.longitude == null) return uni.showToast({ title: "请在地图中选择球场位置", icon: "none" });
  if (!form.name || !(Number(form.price_per_hour) > 0))
    return uni.showToast({ title: "请填写名称和有效价格", icon: "none" });
  loading.value = true;
  try {
    if (form.cover_image) form.cover_image = await uploadedImage(form.cover_image, "court");
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
      >
      <text class="field-label">球场位置 *</text><view class="picker-field">{{ form.address || "请通过地图选择球场位置" }}</view><text v-if="form.city" class="muted small">{{ form.city }} · 城市随地图位置自动填写</text>
      <ActivityLocationSelect label="球场位置" hint="用于导航和距离排序，每片球场独立设置" :city="form.city" :selected="form.latitude !== null" @busy="locationSelecting = $event" @select="point => Object.assign(form, point)" />
      <text class="field-label">场地名称 *</text
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
        ><wd-button block :loading="loading || locationSelecting || imageUploading" @click="save"
          >保存场地</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
