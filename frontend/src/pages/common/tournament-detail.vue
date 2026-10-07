<script setup lang="ts">
import { computed, ref } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import { request } from "../../services/api";
import { payTournament } from "../../services/payment";
import { useSession } from "../../stores/session";
const s = useSession(),
  id = ref(0),
  t = ref<any>(null),
  busy = ref(false);
const reg = computed(() =>
    t.value?.registrations?.find((r: any) => r.user_id === s.user?.id),
  ),
  full = computed(
    () =>
      t.value?.max_participants &&
      t.value.current_participants >= t.value.max_participants,
  ),
  button = computed(() =>
    !s.loggedIn
      ? "登录后报名"
      : t.value?.status !== "open"
        ? "报名未开放"
        : reg.value?.status === "registered"
          ? "去支付"
          : reg.value
            ? "已报名"
            : full.value
              ? "已满员"
              : Number(t.value?.entry_fee) > 0
                ? `报名 ¥${t.value.entry_fee}`
                : "立即报名",
  );
async function load() {
  t.value = await request(`/tournaments/${id.value}`);
}
onLoad((q) => {
  id.value = Number(q?.id);
  s.fetchUser()
    .catch(() => {})
    .finally(load);
});
onShow(() => id.value && load());
async function action() {
  if (!s.requireLogin(`/pages/common/tournament-detail?id=${id.value}`)) return;
  if (reg.value) {
    if (reg.value.status !== "registered") return;
    busy.value = true;
    try {
      await payTournament(id.value);
      uni.showToast({ title: "支付成功", icon: "success" });
      load();
    } finally {
      busy.value = false;
    }
    return;
  }
  if (full.value || t.value.status !== "open") return;
  uni.showModal({
    title: "确认报名",
    content: `确定报名「${t.value.title}」吗？`,
    success: async (r) => {
      if (!r.confirm) return;
      busy.value = true;
      try {
        const x: any = await request(`/tournaments/${id.value}/register`, {
          method: "POST",
        });
        if (x.order)
          await request(`/bookings/${x.order.id}/pay`, { method: "POST" });
        uni.showToast({ title: "报名成功", icon: "success" });
        load();
      } finally {
        busy.value = false;
      }
    },
  });
}
</script>
<template>
  <AppShell back title="赛事详情"
    ><template v-if="t"
      ><view class="detail-photo"
        ><Photo
          width="100%"
          height="100%"
          :src="t.cover_image"
          fallback="/static/tennis.jpg"
          mode="aspectFill" /></view
      ><view class="content detail-content"
        ><text class="tag">{{ t.sport_type || "网球" }}赛事</text
        ><text class="page-title">{{ t.title }}</text
        ><view class="detail-facts"
          ><view class="fact"
            ><wd-icon name="time-line" /><view
              ><text class="strong">{{ t.start_time }}</text
              ><text class="muted">至 {{ t.end_time }}</text></view
            ></view
          ><view class="fact"
            ><wd-icon name="location" /><view
              ><text class="strong">{{ t.club_name }}</text
              ><text class="muted">{{ t.venue_name }}</text></view
            ></view
          ></view
        ><view class="row between section-head"
          ><text class="section-title">参赛人数</text
          ><text class="link"
            >{{ t.current_participants }}/{{ t.max_participants }}</text
          ></view
        ><text class="body-copy">{{
          t.description || "欢迎报名参加本次赛事。"
        }}</text
        ><wd-button
          v-if="t.contact_phone"
          variant="plain"
          size="small"
          @click="uni.makePhoneCall({ phoneNumber: t.contact_phone })"
          >联系主办方</wd-button
        ></view
      ><view class="fixed-action"
        ><text class="price large">¥{{ t.entry_fee || 0 }}</text
        ><wd-button
          :disabled="['已报名', '已满员', '报名未开放'].includes(button)"
          :loading="busy"
          @click="action"
          >{{ button }}</wd-button
        ></view
      ></template
    ><wd-loading v-else
  /></AppShell>
</template>
