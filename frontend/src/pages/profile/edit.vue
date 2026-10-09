<script setup lang="ts">
import { reactive, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import { uploadedImage } from "../../services/media";
import AppShell from "../../components/AppShell.vue";
import NtrpAssessment from "../../components/NtrpAssessment.vue";
import type { RatingResult } from "../../services/rating-assessment";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession(),
  loading = ref(false),
  imageUploading = ref(false),
  isNew = ref(false),
  redirect = ref(""),
  ratingOpen = ref(false),
  profileReady = ref(false),
  levels = [
    "1.0",
    "1.5",
    "2.0",
    "2.5",
    "3.0",
    "3.5",
    "4.0",
    "4.5",
    "5.0",
    "5.5",
    "6.0",
    "6.5",
    "7.0",
  ],
  form = reactive<any>({
    nickname: "",
    phone: "",
    avatar_url: "",
    ntrp_level: "",
  });
onLoad(async (q) => {
  if (!s.requireLogin("/pages/profile/edit")) return;
  isNew.value = q?.new_user === "1";
  redirect.value = decodeURIComponent(String(q?.redirect || ""));
  const u = await s.fetchUser();
  Object.assign(form, {
    nickname: u?.nickname || "",
    phone: u?.phone || "",
    avatar_url: u?.avatar_url || "",
    ntrp_level: u?.ntrp_level ? String(u.ntrp_level) : "",
  });
  profileReady.value = !!u;
});
function ratingCompleted(result: RatingResult) {
  if (!s.user) return;
  form.ntrp_level = Number(result.ntrp_level).toFixed(1);
  s.user.ntrp_level = Number(result.ntrp_level);
  s.user.rating_source = result.rating_source;
}
async function avatar(e: any) {
  if (!profileReady.value || ratingOpen.value || loading.value || imageUploading.value) return;
  imageUploading.value = true;
  try { form.avatar_url = await uploadedImage(e.detail.avatarUrl, "avatar"); }
  catch (error: any) { uni.showToast({ title: error.message || "头像上传失败，请重试", icon: "none" }); }
  finally { imageUploading.value = false; }
}
async function save() {
  if (!profileReady.value || ratingOpen.value || loading.value || imageUploading.value) return;
  if (!form.nickname.trim())
    return uni.showToast({ title: "请输入昵称", icon: "none" });
  if (form.phone && !/^1\d{10}$/.test(form.phone))
    return uni.showToast({ title: "手机号格式不正确", icon: "none" });
  loading.value = true;
  try {
    if (form.avatar_url) form.avatar_url = await uploadedImage(form.avatar_url, "avatar");
    await request("/users/me", {
      method: "PUT",
      data: {
        ...form,
        ntrp_level: form.ntrp_level ? Number(form.ntrp_level) : null,
      },
    });
    await s.fetchUser();
    uni.showToast({ title: "保存成功", icon: "success" });
    setTimeout(
      () =>
        isNew.value
          ? openPage(
              redirect.value.startsWith("/pages/")
                ? redirect.value
                : "/pages/home/index",
            )
          : uni.navigateBack(),
      600,
    );
  } catch (error: any) {
    uni.showToast({ title: error.message || "保存失败，请重试", icon: "none" });
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <page-meta :page-style="ratingOpen ? 'overflow:hidden' : 'overflow:visible'" />
  <AppShell back :title="isNew ? '完善资料' : '个人资料'"
    ><view class="content publish-content"
      ><view class="avatar-edit"
        ><button open-type="chooseAvatar" @chooseavatar="avatar">
          <Photo
            round
            width="88px"
            height="88px"
            :src="form.avatar_url"
            fallback="/static/tennis.jpg"
          /></button></view
      ><text class="field-label">昵称 *</text
      ><input
        class="native-input"
        type="nickname"
        :value="form.nickname"
        placeholder="请输入昵称"
        @input="form.nickname = ($event as any).detail.value"
      /><text class="field-label">手机号</text
      ><wd-input v-model="form.phone" type="tel" :maxlength="11" placeholder="请输入手机号" />
      <view class="rating-label-row"><text class="field-label">NTRP 等级</text>
        <wd-button variant="text" size="small" :disabled="!profileReady || loading || imageUploading" custom-style="color:#147553;padding:0;" @click="ratingOpen = true">测测我的等级</wd-button>
      </view><picker
        :range="levels"
        :value="Math.max(0, levels.indexOf(form.ntrp_level))"
        @change="form.ntrp_level = levels[$event.detail.value]"
        ><view class="picker-field"
          >{{ form.ntrp_level || "请选择"
          }}<wd-icon name="arrow-down" /></view></picker
      ><view class="publish-action"
        ><wd-button block :loading="loading || imageUploading" @click="save"
          >保存</wd-button
        ></view
      ></view
      ><NtrpAssessment v-model="ratingOpen" @completed="ratingCompleted" />
    </AppShell
  >
</template>

<style scoped>
.rating-label-row { display: flex; align-items: center; justify-content: space-between; margin-top: 18px; }
.rating-label-row .field-label { margin: 0; }
</style>
