<script setup lang="ts">
import { ref } from "vue";
import { onReachBottom, onShow } from "@dcloudio/uni-app";
import MainHeader from "../../components/MainHeader.vue";
import { useDiscovery } from "../../stores/discovery";
import AppShell from "../../components/AppShell.vue";
import { request, type PageResult } from "../../services/api";
import { openPage } from "../../utils/navigation";
const location = useDiscovery();
let loadVersion = 0;
let cachedSignature = "", loadedAt = 0;
const cacheTTL = 2 * 60 * 1000;
function querySignature() {
  return JSON.stringify([location.city, keyword.value, sort.value,
    sort.value === "distance" ? location.latitude : null,
    sort.value === "distance" ? location.longitude : null]);
}
const clubs = ref<any[]>([]),
  keyword = ref(""),
  sort = ref("default"),
  page = ref(1),
  more = ref(true),
  loading = ref(false);
async function load(append = false) {
  if (append && loading.value) return;
  const version = ++loadVersion;
  const signature = querySignature();
  if (!append) { clubs.value = []; cachedSignature = ""; loadedAt = 0; }
  if (!location.city) { loading.value = false; return; }
  loading.value = true;
  try {
    const p = append ? page.value + 1 : 1;
    let url = `/clubs?page=${p}&page_size=20&city=${encodeURIComponent(location.city)}`;
    if (keyword.value) url += `&keyword=${encodeURIComponent(keyword.value)}`;
    if (sort.value === "distance" && location.latitude !== null)
      url += `&lat=${location.latitude}&lng=${location.longitude}&sort_by=distance`;
    const r = await request<PageResult<any>>(url);
    if (version !== loadVersion) return;
    clubs.value = append ? [...clubs.value, ...r.items] : r.items;
    page.value = p;
    more.value = r.items.length === 20;
    if (!append) { cachedSignature = signature; loadedAt = Date.now(); }
  } catch (e: any) {
    if (version === loadVersion) uni.showToast({ title: e.message, icon: "none" });
  } finally {
    if (version === loadVersion) loading.value = false;
  }
}
async function setSort(v: string) {
  if (v === "distance") {
    try { await location.coordinates(); }
    catch { uni.showToast({ title: "距离排序需要开启定位", icon: "none" }); return; }
  }
  sort.value = v; await load();
}
onShow(async () => {
  if (!location.city && !location.attempted) {
    try { await location.locate(); }
    catch { uni.showToast({ title: "请手动选择城市", icon: "none" }); }
  }
  if (cachedSignature === querySignature() && Date.now() - loadedAt < cacheTTL) return;
  await load();
});
onReachBottom(() => more.value && load(true));
</script>
<template>
  <AppShell active="clubs"
    ><MainHeader title="订场" @city-change="load()" /><view class="content main-content"
      ><view class="search-card"><wd-search
        v-model="keyword"
        placeholder="搜索俱乐部"
        placeholder-left
        cancel-txt="搜索"
        @search="load()"
        @cancel="load()" /></view><view class="filter-row"
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
          ><text class="muted">{{ c.nearest_venue_name ? c.nearest_venue_name + " · " : "" }}{{ c.venue_address || "球场位置待补充" }}</text
          ><view><text class="tag">网球</text></view></view
        ></view
      ><wd-empty v-if="!loading && !clubs.length" :tip="location.city ? '当前城市暂无球场' : '请先选择城市'"
        ><wd-button size="small" @click="openPage('/pages/publish/club-create')"
          >创建俱乐部</wd-button
        ></wd-empty
      ><wd-loadmore
        v-if="clubs.length"
        :state="loading ? 'loading' : more ? 'default' : 'finished'" /></view
  ></AppShell>
</template>
