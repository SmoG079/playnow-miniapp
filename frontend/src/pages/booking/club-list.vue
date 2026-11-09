<script setup lang="ts">
import BookingClubList from "../../components/BookingClubList.vue";
// #ifdef MP-WEIXIN
import { onShareAppMessage, onShareTimeline } from "@dcloudio/uni-app";
import { enableActivitySharing } from "../../utils/share";

enableActivitySharing();
onShareAppMessage(() => ({
  title: "PlayNow · 预订网球场地",
  path: "/pages/booking/club-list",
  imageUrl: "/static/court.jpg",
}));
onShareTimeline(() => ({
  title: "PlayNow · 预订网球场地",
  imageUrl: "/static/court.jpg",
}));
// #endif
</script>
<template><BookingClubList /></template>
