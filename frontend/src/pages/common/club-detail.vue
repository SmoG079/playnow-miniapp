<script setup lang="ts">
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { useSession } from "../../stores/session";
const session = useSession();
const id = ref(0), club = ref<any>(null), community = ref<any>(null), busy = ref(false), failed = ref(false);
async function load() {
  failed.value = false;
  try { [club.value, community.value] = await Promise.all([request(`/clubs/${id.value}`), request(`/clubs/${id.value}/community`)]); }
  catch { failed.value = true; }
}
onLoad(q => { id.value = Number(q?.id); load(); });
async function change(remove?: string) {
  if (busy.value || !session.requireLogin(`/pages/common/club-detail?id=${id.value}`)) return;
  busy.value = true;
  try {
    await request(`/clubs/${id.value}/community${remove ? '/' + encodeURIComponent(remove) : ''}`, { method: remove || community.value.joined ? "DELETE" : "POST" });
    await load();
  } catch (e: any) { uni.showToast({title: e.message || "操作失败", icon: "none"}); }
  finally { busy.value = false; }
}
function confirmRemove(member: any) {
  uni.showModal({title: "移除成员", content: `确定将${member.name}移出俱乐部？`, success: result => { if (result.confirm) change(member.id); }});
}
</script>
<template>
  <AppShell back title="俱乐部">
    <view class="content club-content" v-if="club && community">
      <view class="club-cover" v-if="club.cover_image">
      <Photo :src="club.cover_image" width="100%" height="180px" /></view>
      <view class="club-identity">
      <Photo v-if="club.logo_image" :src="club.logo_image" round width="64px" height="64px" /><text class="page-title">{{ club.name }}</text>
      <text class="muted">{{ club.city }} · {{ community.count }} 位球友</text></view>
      <view class="community-card"><text class="section-title">社群介绍</text><text class="description">{{ club.description || '欢迎一起打球' }}</text></view>
      <view class="community-card" v-if="club.address"><text>{{ club.address }}</text></view>
      <wd-button v-if="club.contact_phone" variant="plain" block @click="uni.makePhoneCall({phoneNumber: club.contact_phone})">联系组织者</wd-button>
      <view class="community-card">
        <wd-button v-if="!community.owner" block :loading="busy" @click="change()">{{ community.joined ? '退出俱乐部' : '加入俱乐部' }}</wd-button>
        <template v-else><text class="section-title">成员管理</text><view v-for="member in community.members" :key="member.id" class="row between member-row"><text>{{ member.name }}</text><wd-button size="small" variant="text" :disabled="busy" @click="confirmRemove(member)">移除</wd-button></view></template>
      </view>
    </view>
    <view v-else class="content loading-state"><wd-loading v-if="!failed" /><text class="muted">{{ failed ? '俱乐部信息加载失败' : '正在加载俱乐部…' }}</text><wd-button v-if="failed" variant="plain" @click="load">重新加载</wd-button></view>
  </AppShell>
</template>
<style scoped>
.club-cover { overflow:hidden; border-radius:var(--playnow-card-radius); margin-bottom:24px; }
.club-identity { display:flex; flex-direction:column; align-items:flex-start; gap:12px; }
.club-identity .page-title { margin:0; }
.community-card { margin:24px 0; padding:20px 16px; background:var(--playnow-surface); border:1px solid var(--playnow-card-border); border-radius:var(--playnow-card-radius); }
.description { display:block; margin-top:12px; white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.8; color:var(--playnow-muted); }
.member-row { min-height:60px; padding:12px 0; gap:12px; border-bottom:1px solid var(--playnow-card-border); }
.member-row:last-child { border-bottom:0; }
.member-row > text { flex:1; min-width:0; overflow-wrap:anywhere; }
</style>
