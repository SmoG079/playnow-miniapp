<script setup lang="ts">
import { ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
const s = useSession();
const clubId = ref(0),
  items = ref<any[]>([]),
  loading = ref(false),
  initialized = ref(false);
async function load() {
  loading.value = true;
  try {
    items.value = await request(`/clubs/${clubId.value}/venues`);
  } catch (error: any) {
    uni.showToast({ title: error.message || "加载失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
onLoad(async (q) => {
  clubId.value = Number(q?.club_id);
  if (
    !(await s.requireClubAdmin(
      `/pages/admin/venue-manage?club_id=${clubId.value}`,
    ))
  )
    return;
  if (!clubId.value || !s.canManageClub(clubId.value))
    return uni.showToast({ title: "无权管理该俱乐部", icon: "none" });
  initialized.value = true;
  await load();
});
onShow(() => initialized.value && load());
function remove(v: any) {
  uni.showModal({
    title: "删除场地",
    content: `确定删除「${v.name}」吗？`,
    success: async (r) => {
      if (r.confirm) {
        await request(`/venues/${v.id}/with-club/${clubId.value}`, {
          method: "DELETE",
        });
        load();
      }
    },
  });
}
</script>
<template>
  <AppShell back title="场地管理"
    ><view class="content list-content"
      ><view v-for="v in items" :key="v.id" class="record-card"
        ><view class="row between"
          ><text class="strong">{{ v.name }}</text
          ><text class="tag">{{ v.status }}</text></view
        ><text class="price">¥{{ v.price_per_hour }}/小时</text
        ><view class="row gap8"
          ><wd-button
            size="small"
            variant="plain"
            @click="
              uni.navigateTo({
                url: `/pages/publish/venue-manage?club_id=${clubId}&venue_id=${v.id}`,
              })
            "
            >编辑</wd-button
          ><wd-button
            size="small"
            variant="plain"
            @click="
              uni.navigateTo({
                url: `/pages/publish/slot-manage?club_id=${clubId}&venue_id=${v.id}`,
              })
            "
            >时段</wd-button
          ><wd-button
            size="small"
            variant="plain"
            type="danger"
            @click="remove(v)"
            >删除</wd-button
          ></view
        ></view
      ><wd-empty v-if="!loading && !items.length" tip="暂无场地" /> ><wd-button
        block
        @click="
          uni.navigateTo({
            url: '/pages/publish/venue-manage?club_id=' + clubId,
          })
        "
        >新增场地</wd-button
      ></view
    ></AppShell
  >
</template>
