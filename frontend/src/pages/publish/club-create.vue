<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { useDiscovery } from "../../stores/discovery";
import { chooseUploadedImages, uploadedImage } from "../../services/media";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
const discovery = useDiscovery();
const s = useSession(),
  id = ref(0),
  loading = ref(false),
  imageUploading = ref(false),
  locationSelecting = ref(false),
  images = ref<string[]>([]),
  documents = ref<any[]>([]),
  form = reactive<any>({
    city: discovery.city,
    name: "",
    sport_types: ["tennis"],
    description: "",
    rules: "",
    address: "",
    latitude: null,
    longitude: null,
    contact_phone: "",
    logo_image: "",
    opening_time: "08:00",
    closing_time: "22:00",
  });
onLoad(async (q) => {
  if (!s.requireLogin("/pages/publish/club-create")) return;
  id.value = Number(q?.club_id || 0);
  if (!id.value) {
    await discovery.ensureCity().catch(() => uni.showToast({ title: "可手动填写所在城市", icon: "none" }));
    form.city = discovery.city;
  }
  if (id.value) {
    if (
      !(await s.requireClubAdmin(
        `/pages/publish/club-create?mode=edit&club_id=${id.value}`,
      ))
    )
      return;
    if (!s.canManageClub(id.value))
      return uni.showToast({ title: "无权编辑该俱乐部", icon: "none" });
    const c: any = await request(`/clubs/${id.value}`);
    Object.assign(form, c);
    images.value = c.images?.length
      ? c.images
      : c.cover_image
        ? [c.cover_image]
        : [];
    documents.value = c.documents || [];
  }
});
watch(() => discovery.city, value => {
  if (!id.value && form.city !== value) {
    form.city = value; form.address = ""; form.latitude = null; form.longitude = null;
  }
}, { flush: "sync" });
function chooseLocation() {
  if (locationSelecting.value || loading.value) return;
  uni.chooseLocation({
    ...(form.latitude != null && form.longitude != null ? { latitude: form.latitude, longitude: form.longitude } : {}),
    success: async (point) => {
      locationSelecting.value = true;
      try {
        const city = await discovery.selectPoint(point);
        Object.assign(form, { city, address: point.address || point.name, latitude: point.latitude, longitude: point.longitude });
      } catch (error: any) {
        uni.showToast({ title: error.message || "城市识别失败，请重新选择位置", icon: "none" });
      } finally { locationSelecting.value = false; }
    },
    fail: (error) => {
      if (error.errMsg?.includes("auth deny"))
        uni.showModal({ title: "需要位置权限", content: "请在设置中开启位置权限后，通过地图选择俱乐部位置", success: result => result.confirm && uni.openSetting() });
      else if (!error.errMsg?.includes("cancel"))
        uni.showToast({ title: "地图不可用，请稍后重试", icon: "none" });
    },
  });
}
async function chooseImages() {
  if (loading.value || imageUploading.value) return;
  imageUploading.value = true;
  try { await chooseUploadedImages(9 - images.value.length, "post", url => { images.value.push(url); }); }
  catch (error: any) { uni.showToast({ title: error.message || "图片上传失败，请重试", icon: "none" }); }
  finally { imageUploading.value = false; }
}
async function chooseLogo() {
  if (imageUploading.value || loading.value) return;
  imageUploading.value = true;
  try { await chooseUploadedImages(1, "post", url => { form.logo_image = url; }); }
  catch (error: any) { uni.showToast({title: error.message || "上传失败",icon:"none"}); }
  finally { imageUploading.value = false; }
}
async function save() {
  if (loading.value || imageUploading.value || locationSelecting.value) return;

  if (!form.city.trim() || !form.description.trim()) return uni.showToast({ title: "请填写城市和俱乐部介绍", icon: "none" });
  if (!form.name.trim() || !form.contact_phone)
    return uni.showToast({ title: "请填写名称和联系电话", icon: "none" });
  if (
    !/^1\d{10}$/.test(form.contact_phone) &&
    !/^\d{7,12}$/.test(form.contact_phone)
  )
    return uni.showToast({ title: "联系电话格式不正确", icon: "none" });

  loading.value = true;
  try {
    const urls = [];
    for (const p of images.value)
      urls.push(await uploadedImage(p, "post"));
    const data = {
      ...form,
      images: urls,

      cover_image: urls[0] || null,
    };
    await request(id.value ? `/clubs/${id.value}` : "/clubs", {
      method: id.value ? "PUT" : "POST",
      data,
    });
    await s.fetchUser();
    uni.showToast({ title: id.value ? "保存成功" : "已提交，等待系统管理员审核", icon: "none" });
    setTimeout(() => uni.navigateBack(), 600);
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back :title="id ? '编辑俱乐部' : '创建俱乐部'"
    ><view class="content publish-content"
      >
      <text class="field-label">所在城市 *</text><wd-input v-model="form.city" placeholder="例如：上海市" /><text class="field-label">俱乐部名称 *</text
      ><wd-input v-model="form.name" /><text class="field-label"
        >联系电话 *</text
      ><wd-input v-model="form.contact_phone" type="number" /><text
        class="field-label"
        >具体地点（选填）</text
      ><view class="picker-field" @click="chooseLocation"
        ><text>{{ form.address || "在地图中选择" }}</text
        ><wd-icon name="location" /></view
      ><wd-button v-if="form.address" size="small" variant="text" @click="form.address='';form.latitude=null;form.longitude=null">清除具体地点</wd-button><text class="muted small">{{ locationSelecting ? '正在识别城市…' : (form.city ? form.city : '请选择地图位置') }}</text>
      <text class="field-label">介绍 *</text
      ><wd-textarea
        v-model="form.description"
        :maxlength="1000"
        show-word-limit
      /><text class="field-label">俱乐部 LOGO（选填）</text><view class="image-grid"><Photo v-if="form.logo_image" :src="form.logo_image" round width="72px" height="72px" @click="form.logo_image = ''" /><wd-button size="small" variant="plain" :disabled="imageUploading" @click="chooseLogo">上传 LOGO</wd-button></view><text class="field-label">社群宣传图（选填，最多9张）</text
      ><view class="image-grid"
        ><Photo
          v-for="(x, i) in images"
          :key="x"
          width="72px"
          height="72px"
          :src="x"
          @click="images.splice(i, 1)" /><button
          class="upload-box"
          @click="chooseImages"
        >
          <wd-icon name="plus" /></button></view
      ><view class="publish-action"
        ><wd-button block :loading="loading || imageUploading || locationSelecting" @click="save"
          >{{ id ? "保存俱乐部" : "提交俱乐部申请" }}</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
