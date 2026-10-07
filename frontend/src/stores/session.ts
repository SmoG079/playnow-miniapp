import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { request, clearTokens } from "../services/api";

export interface User {
  id: number;
  nickname?: string;
  avatar_url?: string;
  phone?: string;
  role?: string;
  managed_club_ids?: number[];
  ntrp_level?: number;
  city?: string;
}

export const useSession = defineStore("session", () => {
  const user = ref<User | null>(null);
  const loading = ref(false);
  const accessToken = ref("");
  const refreshToken = ref("");
  const loggedIn = computed(() => !!accessToken.value);
  const isClubAdmin = computed(() =>
    ["club_admin", "platform_admin"].includes(user.value?.role || ""),
  );
  const isPlatformAdmin = computed(() => user.value?.role === "platform_admin");

  function syncTokens() {
    accessToken.value = String(uni.getStorageSync("access_token") || "");
    refreshToken.value = String(uni.getStorageSync("refresh_token") || "");
  }

  function setTokens(access: string, refresh: string) {
    accessToken.value = access;
    refreshToken.value = refresh;
    uni.setStorageSync("access_token", access);
    uni.setStorageSync("refresh_token", refresh);
  }

  syncTokens();

  async function fetchUser() {
    syncTokens();
    if (!loggedIn.value) {
      user.value = null;
      return null;
    }
    loading.value = true;
    try {
      user.value = await request<User>("/users/me");
      return user.value;
    } catch (error) {
      syncTokens();
      if (!loggedIn.value) user.value = null;
      throw error;
    } finally {
      loading.value = false;
    }
  }
  function requireLogin(redirect?: string) {
    syncTokens();
    if (loggedIn.value) return true;
    uni.navigateTo({
      url: `/pages/common/login${redirect ? `?redirect=${encodeURIComponent(redirect)}` : ""}`,
    });
    return false;
  }
  async function requireClubAdmin(redirect?: string) {
    if (!requireLogin(redirect)) return false;
    if (!user.value) {
      try {
        await fetchUser();
      } catch {
        return false;
      }
    }
    if (isClubAdmin.value) return true;
    uni.showToast({ title: "需要俱乐部管理员权限", icon: "none" });
    return false;
  }

  function canManageClub(clubId: number) {
    return (
      isPlatformAdmin.value ||
      (user.value?.managed_club_ids || []).includes(clubId)
    );
  }

  function logout() {
    clearTokens();
    accessToken.value = "";
    refreshToken.value = "";
    user.value = null;
    uni.reLaunch({ url: "/pages/home/index" });
  }
  return {
    user,
    loading,
    loggedIn,
    isClubAdmin,
    isPlatformAdmin,
    setTokens,
    syncTokens,
    fetchUser,
    requireLogin,
    requireClubAdmin,
    canManageClub,
    logout,
  };
});
