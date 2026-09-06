<script setup lang="ts">
import { reactive, ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, uploadFile } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession(),
  loading = ref(false),
  isNew = ref(false),
  redirect = ref(""),
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
});
function avatar(e: any) {
  form.avatar_url = e.detail.avatarUrl;
}
async function phone(e: any) {
  if (!e.detail.code)
    return uni.showToast({ title: "未授权，可手动填写", icon: "none" });
  await request("/auth/phone", {
    method: "POST",
    data: { code: e.detail.code },
  });
  Object.assign(form, await s.fetchUser());
  uni.showToast({ title: "已获取手机号", icon: "success" });
}
async function save() {
  if (!form.nickname.trim())
    return uni.showToast({ title: "请输入昵称", icon: "none" });
  if (form.phone && !/^1\d{10}$/.test(form.phone))
    return uni.showToast({ title: "手机号格式不正确", icon: "none" });
  loading.value = true;
  try {
    if (form.avatar_url && !/^https?:/.test(form.avatar_url))
      form.avatar_url = (await uploadFile(form.avatar_url)).url;
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
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back :title="isNew ? '完善资料' : '个人资料'"
    ><view class="content publish-content"
      ><view class="avatar-edit"
        ><button open-type="chooseAvatar" @chooseavatar="avatar">
          <wd-img
            round
            width="88px"
            height="88px"
            :src="form.avatar_url || '/static/tennis.jpg'"
          /></button></view
      ><text class="field-label">昵称 *</text
      ><input
        class="native-input"
        type="nickname"
        :value="form.nickname"
        placeholder="请输入昵称"
        @input="form.nickname = ($event as any).detail.value"
      /><text class="field-label">手机号</text
      ><wd-input
        v-model="form.phone"
        type="number"
        placeholder="用于预约与活动联系"
      /><wd-button
        block
        variant="plain"
        open-type="getPhoneNumber"
        @getphonenumber="phone"
      >
        微信手机号快捷填写</wd-button
      ><text class="field-label">NTRP 等级</text
      ><picker
        :range="levels"
        :value="Math.max(0, levels.indexOf(form.ntrp_level))"
        @change="form.ntrp_level = levels[$event.detail.value]"
        ><view class="picker-field"
          >{{ form.ntrp_level || "请选择"
          }}<wd-icon name="arrow-down" /></view></picker
      ><view class="publish-action"
        ><wd-button block :loading="loading" @click="save"
          >保存</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
