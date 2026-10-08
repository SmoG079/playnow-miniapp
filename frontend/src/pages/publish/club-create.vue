<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { useDiscovery } from "../../stores/discovery";
import { chooseUploadedImages, uploadedImage } from "../../services/media";
import { request, uploadFile } from "../../services/api";
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
    opening_time: "08:00",
    closing_time: "22:00",
  });
onLoad(async (q) => {
  if (!s.requireLogin("/pages/publish/club-create")) return;
  id.value = Number(q?.club_id || 0);
  if (!id.value) {
    await discovery.ensureCity().catch(() => uni.showToast({ title: "请在地图中选择俱乐部位置", icon: "none" }));
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
function chooseDocument() {
  const remain = 5 - documents.value.length;
  if (remain <= 0)
    return uni.showToast({ title: "最多上传5个文件", icon: "none" });
  uni.chooseMessageFile({
    count: remain,
    type: "file",
    extension: ["pdf"],
    success: (result) => {
      const files = result.tempFiles || [];
      const tooLarge = files.find((file) => file.size > 10 * 1024 * 1024);
      if (tooLarge)
        return uni.showToast({
          title: `${tooLarge.name || "文件"}超过10MB`,
          icon: "none",
        });
      documents.value.push(
        ...files.map((file) => ({
          name: file.name,
          path: file.path,
          size: file.size,
        })),
      );
    },
  });
}
async function save() {
  if (loading.value || imageUploading.value || locationSelecting.value) return;
  if (form.latitude == null || form.longitude == null) return uni.showToast({ title: "请在地图中选择俱乐部位置", icon: "none" });
  if (!form.city) return uni.showToast({ title: "请在地图中选择俱乐部位置", icon: "none" });
  if (!form.name.trim() || !form.contact_phone || !form.address.trim())
    return uni.showToast({ title: "请填写名称、地址和联系电话", icon: "none" });
  if (
    !/^1\d{10}$/.test(form.contact_phone) &&
    !/^\d{7,12}$/.test(form.contact_phone)
  )
    return uni.showToast({ title: "联系电话格式不正确", icon: "none" });
  if (form.closing_time <= form.opening_time)
    return uni.showToast({ title: "营业结束时间需晚于开始时间", icon: "none" });
  loading.value = true;
  try {
    const urls = [];
    for (const p of images.value)
      urls.push(await uploadedImage(p, "post"));
    const uploadedDocuments = [];
    for (const doc of documents.value) {
      if (doc.url) uploadedDocuments.push(doc);
      else {
        const uploaded = await uploadFile(doc.path, "doc");
        uploadedDocuments.push({
          name: doc.name,
          url: uploaded.url,
          size: doc.size,
        });
      }
    }
    const data = {
      ...form,
      images: urls,
      documents: uploadedDocuments,
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
      <text class="field-label">俱乐部名称 *</text
      ><wd-input v-model="form.name" /><text class="field-label"
        >联系电话 *</text
      ><wd-input v-model="form.contact_phone" type="number" /><text
        class="field-label"
        >俱乐部位置 *</text
      ><view class="picker-field" @click="chooseLocation"
        ><text>{{ form.address || "在地图中选择" }}</text
        ><wd-icon name="location" /></view
      ><text class="muted small">{{ locationSelecting ? '正在识别城市…' : (form.city ? form.city + ' · 城市根据地图位置自动填写' : '选择地图位置后自动获取城市') }}</text>
      <text class="field-label">营业时间</text
      ><view class="form-two"
        ><picker
          mode="time"
          :value="form.opening_time"
          @change="form.opening_time = $event.detail.value"
          ><view class="picker-field">{{ form.opening_time }}</view></picker
        ><picker
          mode="time"
          :value="form.closing_time"
          @change="form.closing_time = $event.detail.value"
          ><view class="picker-field">{{ form.closing_time }}</view></picker
        ></view
      ><text class="field-label">介绍</text
      ><wd-textarea
        v-model="form.description"
        :maxlength="1000"
        show-word-limit
      /><text class="field-label">预订规则</text
      ><wd-textarea v-model="form.rules" :maxlength="1000" /><text
        class="field-label"
        >场馆图片（最多9张）</text
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
      ><text class="field-label">场地规则 PDF（最多5个，每个10MB）</text
      ><view class="menu-list"
        ><wd-cell
          v-for="(doc, i) in documents"
          :key="doc.url || doc.path"
          :title="doc.name"
          :label="doc.size ? `${(doc.size / 1024 / 1024).toFixed(1)} MB` : ''"
          ><template #default
            ><text class="link" @click="documents.splice(i, 1)"
              >删除</text
            ></template
          ></wd-cell
        ><wd-button
          v-if="documents.length < 5"
          size="small"
          variant="plain"
          @click="chooseDocument"
          >添加 PDF</wd-button
        ></view
      ><view class="publish-action"
        ><wd-button block :loading="loading || imageUploading || locationSelecting" @click="save"
          >{{ id ? "保存俱乐部" : "提交俱乐部申请" }}</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
