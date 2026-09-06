<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession(),
  clubs = ref<any[]>([]),
  loading = ref(false);
onShow(async () => {
  if (!(await s.requireClubAdmin("/pages/admin/club-manage"))) return;
  loading.value = true;
  try {
    clubs.value = await Promise.all(
      (s.user?.managed_club_ids || []).map((id) => request(`/clubs/${id}`)),
    );
  } catch (error: any) {
    uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
});
</script>
<template>
  <AppShell back title="俱乐部管理"
    ><view class="content list-content"
      ><view v-for="c in clubs" :key="c.id" class="record-card"
        ><view class="row gap8"
          ><wd-img
            width="64px"
            height="64px"
            :src="c.cover_image || '/static/court.jpg'"
          /><view
            ><text class="strong">{{ c.name }}</text
            ><text class="muted small">{{ c.address }}</text></view
          ></view
        ><wd-button
          size="small"
          variant="plain"
          @click="
            uni.navigateTo({
              url: '/pages/publish/club-create?mode=edit&club_id=' + c.id,
            })
          "
          >编辑</wd-button
        ></view
      ><wd-empty v-if="!loading && !clubs.length" tip="暂无可管理的俱乐部" />
      ><wd-button
        block
        @click="uni.navigateTo({ url: '/pages/publish/club-create' })"
        >创建俱乐部</wd-button
      ></view
    ></AppShell
  >
</template>
