<script setup lang="ts">
import { ref } from "vue";
import { onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { listAll } from "../../services/api";
import { useSession } from "../../stores/session";
import { openPage } from "../../utils/navigation";
const s = useSession(),
  items = ref<any[]>([]),
  loading = ref(false);
onShow(async () => {
  if (!s.requireLogin("/pages/profile/my-registrations")) return;
  loading.value = true;
  try {
    items.value = await listAll("/users/me/registrations");
  } catch (error: any) {
    uni.showToast({ title: error.message || "报名记录加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
});
</script>
<template>
  <AppShell back title="我的报名"
    ><view class="content list-content"
      ><view
        v-for="r in items"
        :key="r.ref_type + ':' + r.id"
        class="record-card"
        @click="openPage((r.ref_type === 'tournament' ? '/pages/common/tournament-detail?id=' : '/pages/common/post-detail?id=') + r.ref_id)"
        ><view class="row between"
          ><text class="strong">{{ r.title }}</text
          ><text class="tag">{{
            r.status === "pending"
              ? "待审核"
              : r.status === "approved"
                ? "已通过"
                : r.status === "confirmed"
                  ? "已确认"
                  : r.status === "registered"
                    ? "已报名"
                    : r.status === "rejected"
                      ? "未通过"
                      : r.status
          }}</text></view
        ><text class="muted small"
          >{{ r.preferred_date }} {{ r.preferred_start }}</text
        ></view
      ><wd-empty v-if="!loading && !items.length" tip="还没有报名活动" /></view
  ></AppShell>
</template>
