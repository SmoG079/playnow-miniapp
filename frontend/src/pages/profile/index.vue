<script setup lang="ts">
import { computed } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession();
onShow(() => s.fetchUser().catch(() => {}));
const menus = computed(() => {
  const common = [
    ["calendar-line", "我的预约", "/pages/profile/my-bookings"],
    ["user", "我的报名", "/pages/profile/my-registrations"],
    ["edit", "活动管理", "/pages/profile/my-posts"],
    ["notification", "系统通知", "/pages/message/list"],
  ];
  if (s.isClubAdmin && s.user?.managed_club_ids?.length)
    common.splice(
      1,
      0,
      ["home", "俱乐部管理", "/pages/profile/club-dashboard"],
      ["money-circle", "分账记录", "/pages/profile/settlement-list"],
    );
  return common;
});
function logout() {
  uni.showModal({
    title: "退出登录",
    content: "确定要退出登录吗？",
    success: (r) => r.confirm && s.logout(),
  });
}
</script>
<template>
  <AppShell active="profile"
    ><view class="content"
      ><view class="page-heading"
        ><text class="brand"
          >PlayNow<text class="brand-dot">.</text></text
        ></view
      ><template v-if="s.loggedIn"
        ><view class="profile-header" @click="openPage('/pages/profile/edit')"
          ><wd-img
            round
            width="75px"
            height="75px"
            :src="s.user?.avatar_url || '/static/tennis.jpg'"
          /><view
            ><text class="page-title compact">{{
              s.user?.nickname || "网球爱好者"
            }}</text
            ><text class="muted">{{ s.user?.city || "未设置城市" }}</text
            ><text v-if="s.user?.ntrp_level" class="tag yellow"
              >NTRP {{ s.user.ntrp_level }}</text
            ></view
          ></view
        ><view class="menu-list"
          ><wd-cell
            v-for="m in menus"
            :key="m[2]"
            :title="m[1]"
            :icon="m[0]"
            is-link
            @click="openPage(m[2])" /><wd-cell
            title="编辑个人资料"
            icon="user"
            is-link
            @click="openPage('/pages/profile/edit')" /></view
        ><view class="publish-action"
          ><wd-button block variant="plain" type="danger" @click="logout"
            >退出登录</wd-button
          ></view
        ></template
      ><view v-else class="empty-state"
        ><wd-icon name="user" size="52px" color="#147553" /><text
          class="section-title"
          >登录后开启完整体验</text
        ><text class="muted">报名、订场、发布活动与管理俱乐部</text
        ><wd-button @click="openPage('/pages/common/login')"
          >微信登录</wd-button
        ></view
      ></view
    ></AppShell
  >
</template>
