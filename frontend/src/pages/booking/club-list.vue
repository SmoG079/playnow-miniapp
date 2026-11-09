<script setup lang="ts">
import BookingClubList from "../../components/BookingClubList.vue";
// #ifdef MP-WEIXIN
import { onShow, onShareAppMessage, onShareTimeline } from "@dcloudio/uni-app";
import { enableActivitySharing } from "../../utils/share";

onShow(() => enableActivitySharing());
onShareAppMessage(() => ({
  title: "e球有约 · 发现网球俱乐部",
  path: "/pages/booking/club-list",
  imageUrl: "/static/court.jpg",
}));
onShareTimeline(() => ({
  title: "e球有约 · 发现网球俱乐部",
  imageUrl: "/static/court.jpg",
}));
// #endif
</script>
<template><BookingClubList /></template>
