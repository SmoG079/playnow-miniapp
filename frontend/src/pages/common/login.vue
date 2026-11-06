<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
import { assertWeChatAppId } from "../../services/wechat-login";
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
  if (loading.value) return;
  if (!agreed.value)
    return uni.showToast({ title: "请先同意用户协议", icon: "none" });
  loading.value = true;
  try {
    // #ifdef MP-WEIXIN
    assertWeChatAppId(uni.getAccountInfoSync().miniProgram.appId);
    // #endif
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
  <AppShell back title="登录" simple-header
    ><view class="login-page"
      ><view class="login-brand">PlayNow</view><text class="page-title">下一场球，从这里开始</text><text class="body-copy">登录后加入球局、报名比赛，与球友保持联系。</text
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
<style scoped>
.login-brand { font-size:32px; font-weight:700; color:var(--playnow-brand); letter-spacing:-1px; margin:24px 0 8px; }
.login-page { min-height:0; padding:24px var(--playnow-gutter) 48px; }
.login-page .page-title { font-size:24px; margin:0; }
.agreement { margin-top:48px; align-items:flex-start; line-height:1.8; color:var(--playnow-muted); }
.agreement checkbox { flex:none; }
</style>
