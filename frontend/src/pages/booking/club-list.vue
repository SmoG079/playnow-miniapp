<script setup lang="ts">
import { ref } from "vue";
import { onReachBottom, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { openPage } from "../../utils/navigation";
const clubs = ref<any[]>([]),
  keyword = ref(""),
  sort = ref("default"),
  page = ref(1),
  more = ref(true),
  loading = ref(false),
  location = ref<any>(null);
async function locate() {
  try {
    location.value = await uni.getLocation({ type: "gcj02" });
  } catch {
    location.value = null;
  }
}
async function load(append = false) {
  if (loading.value) return;
  loading.value = true;
  try {
    const p = append ? page.value + 1 : 1;
    let url = `/clubs?page=${p}&page_size=20`;
    if (keyword.value) url += `&keyword=${encodeURIComponent(keyword.value)}`;
    if (sort.value === "distance" && location.value)
      url += `&lat=${location.value.latitude}&lng=${location.value.longitude}&sort_by=distance`;
    const r = await request<PageResult<any>>(url);
    clubs.value = append ? [...clubs.value, ...r.items] : r.items;
    page.value = p;
    more.value = r.items.length === 20;
  } catch (e: any) {
    uni.showToast({ title: e.message, icon: "none" });
  } finally {
    loading.value = false;
  }
}
async function setSort(v: string) {
  if (v === "distance" && !location.value) await locate();
  sort.value = location.value || v === "default" ? v : "default";
  load();
}
onShow(() => {
  locate();
  load();
});
onReachBottom(() => more.value && load(true));
</script>
<template>
  <AppShell active="clubs"
    ><view class="content"
      ><view class="page-heading"><text class="page-title">找球场</text></view
      ><wd-search
        v-model="keyword"
        placeholder="搜索俱乐部"
        cancel-txt="搜索"
        @search="load()"
        @cancel="load()" /><view class="filter-row"
        ><wd-button
          size="small"
          :type="sort === 'default' ? 'primary' : 'info'"
          variant="plain"
          @click="setSort('default')"
          >默认</wd-button
        ><wd-button
          size="small"
          :type="sort === 'distance' ? 'primary' : 'info'"
          variant="plain"
          @click="setSort('distance')"
          >距离最近</wd-button
        ></view
      ><view
        v-for="c in clubs"
        :key="c.id"
        class="venue-card"
        @click="openPage('/pages/booking/venue-detail?id=' + c.id)"
        ><view class="venue-photo"
          ><Photo
            width="100%"
            height="100%"
            :src="c.cover_image"
            fallback="/static/court.jpg"
            mode="aspectFill"
          /><text v-if="c.distance != null" class="distance-badge"
            >{{ c.distance }}km</text
          ></view
        ><view class="venue-card-body"
          ><text class="section-title">{{ c.name }}</text
          ><text class="muted">{{ c.address || "暂无地址" }}</text
          ><view><text class="tag">网球</text></view></view
        ></view
      ><wd-empty v-if="!loading && !clubs.length" tip="暂未找到俱乐部"
        ><wd-button size="small" @click="openPage('/pages/publish/club-create')"
          >创建俱乐部</wd-button
        ></wd-empty
      ><wd-loadmore
        v-if="clubs.length"
        :state="loading ? 'loading' : more ? 'default' : 'finished'" /></view
  ></AppShell>
</template>
