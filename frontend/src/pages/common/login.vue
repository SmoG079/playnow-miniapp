<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const agreed = ref(false),
  loading = ref(false),
  redirect = ref("");
const s = useSession();
onLoad((q) => {
  redirect.value = decodeURIComponent(String(q?.redirect || ""));
  s.syncTokens();
  if (s.loggedIn) {
    openPage(
      redirect.value.startsWith("/pages/")
        ? redirect.value
        : "/pages/home/index",
    );
  }
});

function getWeChatCode() {
  return new Promise<string>((resolve, reject) => {
    uni.login({
      provider: "weixin",
      success: (result) =>
        result.code
          ? resolve(result.code)
          : reject(new Error("未获取到微信登录凭证")),
      fail: reject,
    });
  });
}

async function login() {
  if (!agreed.value)
    return uni.showToast({ title: "请先同意用户协议", icon: "none" });
  loading.value = true;
  try {
    const code = await getWeChatCode();
    const tokens: any = await request("/auth/login", {
      method: "POST",
      data: { code },
      skipAuth: true,
    });
    if (!tokens.access_token || !tokens.refresh_token)
      throw new Error("登录响应缺少令牌");
    s.setTokens(tokens.access_token, tokens.refresh_token);
    const user = await s.fetchUser();
    if (!user?.nickname)
      return uni.reLaunch({
        url: `/pages/profile/edit?new_user=1&redirect=${encodeURIComponent(redirect.value)}`,
      });
    openPage(
      redirect.value.startsWith("/pages/")
        ? redirect.value
        : "/pages/home/index",
    );
  } catch (e: any) {
    uni.showToast({ title: e.message || "登录失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back title="登录"
    ><view class="login-page"
      ><text class="brand">PlayNow<text class="brand-dot">.</text></text
      ><text class="page-title">登录后，上场见。</text
      ><text class="muted">微信快捷登录，安全保存你的预约与活动记录</text
      ><label class="agreement" @click="agreed = !agreed"
        ><checkbox :checked="agreed" color="#147553" /><text
          >我已阅读并同意《用户协议》和《隐私政策》</text
        ></label
      ><wd-button block :loading="loading" @click="login"
        >微信登录</wd-button
      ></view
    ></AppShell
  >
</template>
