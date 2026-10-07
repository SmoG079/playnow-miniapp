<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
const name = ref("球友");
onLoad((q) => {
  if (q?.nickname) name.value = decodeURIComponent(String(q.nickname));
});
</script>
<template>
  <AppShell back title="球友资料"
    ><view class="content"
      ><view class="profile-header"
        ><view class="profile-avatar">{{ name.slice(0, 1) }}</view
        ><view
          ><text class="page-title compact">{{ name }}</text
          ><text class="muted">PlayNow 球友</text></view
        ></view
      ><text class="notice"
        >为保护用户隐私，仅展示活动中公开的信息。</text
      ></view
    ></AppShell
  >
</template>
