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
  let generation = 0;
  const loggedIn = computed(() => !!accessToken.value);
  const isClubAdmin = computed(() =>
    ["club_admin", "platform_admin"].includes(user.value?.role || ""),
  );
  const isPlatformAdmin = computed(() => user.value?.role === "platform_admin");
  const canPublishTournament = computed(() => loggedIn.value);

  function syncTokens() {
    accessToken.value = String(uni.getStorageSync("access_token") || "");
    refreshToken.value = String(uni.getStorageSync("refresh_token") || "");
    if (!accessToken.value) user.value = null;
  }

  function setTokens(access: string, refresh: string) {
    generation++;
    loading.value = false;
    user.value = null;
    uni.removeStorageSync("registered_post_ids");
    uni.removeStorageSync("booking_return");
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
    const currentGeneration = generation;
    try {
      const fetched = await request<User>("/users/me");
      if (currentGeneration !== generation || !uni.getStorageSync("access_token"))
        return null;
      user.value = fetched;
      return user.value;
    } catch (error) {
      if (currentGeneration === generation) syncTokens();
      throw error;
    } finally {
      if (currentGeneration === generation) loading.value = false;
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
    try {
      await fetchUser();
    } catch {
      user.value = null;
      return false;
    }
    if (isClubAdmin.value) return true;
    uni.showToast({ title: "需要俱乐部管理员权限", icon: "none" });
    return false;
  }

  function canManageClub(clubId: number) {
    return (
      isPlatformAdmin.value ||
      (user.value?.role === "club_admin" &&
        (user.value.managed_club_ids || []).includes(clubId))
    );
  }

  function logout() {
    generation++;
    loading.value = false;
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
    canPublishTournament,
    setTokens,
    syncTokens,
    fetchUser,
    requireLogin,
    requireClubAdmin,
    canManageClub,
    logout,
  };
});
