<script setup lang="ts">
import { reactive, ref, computed } from "vue";
import { onLoad, onShow } from "@dcloudio/uni-app";
import AppShell from "../../components/AppShell.vue";
import TournamentSchedulePreview from "../../components/TournamentSchedulePreview.vue";
import { listAll, request, uploadFile } from "../../services/api";
import { useSession } from "../../stores/session";
import {
  defaultConfig,
  formatNames,
  disciplineNames,
  validateConfig,
  localTime,
  getTournament,
} from "../../services/tournaments";
import { buildSchedulePreview } from "../../services/tournament-preview";
const session = useSession(),
  clubs = ref<any[]>([]),
  clubIndex = ref(0),
  loading = ref(false),
  editId = ref(0),
  panels = ref<string[]>([]),
  images = ref<string[]>([]),
  preview = ref<any>(null),
  previewVisible = ref(false),
  linked = ref<any>(null);
const cfg = reactive(defaultConfig());
const form = reactive({
  title: "",
  auto_title: false,
  start_date: "",
  end_date: "",
  start: "09:00",
  end: "17:00",
  entry_fee: "0",
  max_participants: 16,
  description:
    "欢迎参加我们的网球比赛！\n时间：{{日期}} {{时间}}\n地点：{{地点}}",
  prize: "",
  address: "",
  contact_name: "",
  contact_phone: "",
  registration_hours: "0",
  cancellation_hours: "1",
  courts: "1号场地",
});
const placeholderHint =
  "支持日期、时间、地点占位符：" +
  ["日期", "时间", "地点"].map((x) => "{{" + x + "}}").join(" ");
const autoTitle = computed(
  () => `${form.start_date} ${disciplineNames[cfg.discipline]}比赛`,
);
const summary = computed(
  () =>
    `${formatNames[cfg.format]} · ${disciplineNames[cfg.discipline]} · ${cfg.group_count}组`,
);
onLoad(async (q) => {
  const redirect =
    "/pages/publish/tournament-create" + (q?.id ? `?id=${q.id}` : "");
  if (!session.requireLogin(redirect)) return;
  await session.fetchUser();
  if (!session.canPublishTournament) {
    uni.showToast({ title: "需要主办俱乐部管理权限", icon: "none" });
    uni.switchTab({ url: "/pages/publish/post-create" });
    return;
  }
  const all = await listAll<any>("/clubs");
  clubs.value = session.isPlatformAdmin
    ? all
    : all.filter((c) => session.canManageClub(c.id));
  if (!clubs.value.length) {
    uni.showToast({ title: "需要主办俱乐部管理权限", icon: "none" });
    return;
  }
  form.start_date = form.end_date = new Date(
    Date.now() + 86400000 + 8 * 3600000,
  )
    .toISOString()
    .slice(0, 10);
  editId.value = Number(q?.id || 0);
  if (editId.value) {
    const t = await getTournament(editId.value);
    clubIndex.value = clubs.value.findIndex((c) => c.id === t.club_id);
    const start = localTime(t.start_time),
      end = localTime(t.end_time);
    Object.assign(form, {
      title: t.title,
      auto_title: t.auto_title,
      start_date: start.slice(0, 10),
      end_date: end.slice(0, 10),
      start: start.slice(11),
      end: end.slice(11),
      entry_fee: String(t.entry_fee),
      max_participants: t.max_participants,
      description: t.description_template || t.description,
      prize: t.prize || "",
      address: t.address || "",
      contact_name: t.contact_name || "",
      contact_phone: t.contact_phone || "",
    });
    if (t.config) Object.assign(cfg, t.config);
    form.courts = cfg.courts.join("\n");
    images.value = t.images || [];
    form.registration_hours = String(
      (new Date(t.start_time + "Z").getTime() -
        new Date((t.registration_deadline || t.start_time) + "Z").getTime()) /
        3600000,
    );
    form.cancellation_hours = t.cancellation_deadline
      ? String(
          (new Date(t.start_time + "Z").getTime() -
            new Date(t.cancellation_deadline + "Z").getTime()) /
            3600000,
        )
      : "1";
  }
});
onShow(() => {
  const x = uni.getStorageSync("booking_return");
  if (x) {
    linked.value = x;
    form.address = x.venue_name || form.address;
    uni.removeStorageSync("booking_return");
  }
});
function fail(message: string, panel = "advanced") {
  panels.value = [...new Set([...panels.value, panel])];
  uni.showToast({ title: message, icon: "none" });
  uni.pageScrollTo({ selector: "#" + panel, duration: 200 });
}
function payload(previewOnly = false) {
  cfg.group_count = Number(cfg.group_count);
  cfg.match_minutes = Number(cfg.match_minutes);
  cfg.qualifiers_per_group = Number(cfg.qualifiers_per_group);
  cfg.courts = form.courts
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  if (cfg.format === "knockout") cfg.allow_draw = false;
  const error = validateConfig(cfg, Number(form.max_participants));
  if (error) {
    fail(error, "rules");
    return;
  }
  const title = form.auto_title ? autoTitle.value : form.title.trim();
  const start = new Date(`${form.start_date}T${form.start}:00+08:00`),
    end = new Date(`${form.end_date}T${form.end}:00+08:00`);
  if (
    (!previewOnly && (!title || !clubs.value[clubIndex.value])) ||
    isNaN(+start) ||
    isNaN(+end) ||
    end <= start
  ) {
    fail("请检查名称、主办俱乐部和时间", "basic");
    return;
  }
  if (!previewOnly && !form.address.trim() && !linked.value?.venue_id) {
    fail("请填写比赛地点或关联场地", "basic");
    return;
  }
  if (
    !previewOnly &&
    (Number(form.entry_fee) < 0 || !Number.isFinite(Number(form.entry_fee)))
  ) {
    fail("请检查报名费");
    return;
  }
  if (
    !previewOnly &&
    [form.registration_hours, form.cancellation_hours].some(
      (x) => !Number.isFinite(Number(x)) || Number(x) < 0,
    )
  ) {
    fail("截止时长须为非负数字");
    return;
  }
  return {
    club_id: clubs.value[clubIndex.value]?.id || 0,
    title,
    auto_title: form.auto_title,
    sport_type: "网球",
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    entry_fee: Number(form.entry_fee),
    max_participants: Number(form.max_participants),
    description: form.description,
    prize: form.prize,
    address: form.address,
    contact_name: form.contact_name,
    contact_phone: form.contact_phone,
    images: [] as string[],
    venue_id: linked.value?.venue_id || null,
    lock_venue: false,
    config: { ...cfg },
    registration_deadline: new Date(
      +start - (previewOnly ? 0 : Number(form.registration_hours)) * 3600000,
    ).toISOString(),
    cancellation_deadline: new Date(
      +start - (previewOnly ? 1 : Number(form.cancellation_hours)) * 3600000,
    ).toISOString(),
  };
}
async function showPreview() {
  const data = payload(true);
  if (!data) return;
  loading.value = true;
  try {
    preview.value = buildSchedulePreview(
      cfg,
      data.max_participants,
      data.start_time,
      data.end_time,
    );
    previewVisible.value = true;
  } catch (e: any) {
    fail(e.message || "赛程预览失败", "rules");
  } finally {
    loading.value = false;
  }
}
function pick() {
  uni.chooseImage({
    count: 6 - images.value.length,
    sizeType: ["compressed"],
    success: (r) => images.value.push(...r.tempFilePaths),
  });
}
async function save() {
  const data = payload();
  if (!data || loading.value) return;
  loading.value = true;
  try {
    for (const img of images.value)
      data.images.push(
        /^https?:/.test(img) ? img : (await uploadFile(img, "post")).url,
      );
    const t: any = await request(
      editId.value ? `/tournaments/${editId.value}` : "/tournaments",
      { method: editId.value ? "PUT" : "POST", data },
    );
    uni.redirectTo({ url: `/pages/common/tournament-detail?id=${t.id}` });
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back :title="editId ? '编辑赛事' : '创建赛事'"
    ><view class="content publish-content">
      <view id="basic"
        ><text class="section-title">基本信息</text
        ><text class="field-label">主办俱乐部</text
        ><picker
          :range="clubs.map((c) => c.name)"
          :value="clubIndex"
          @change="clubIndex = Number($event.detail.value)"
          ><view class="picker-field">{{
            clubs[clubIndex]?.name || "无可管理俱乐部"
          }}</view></picker
        >
        <text class="field-label">赛事名称 *</text
        ><wd-input
          v-model="form.title"
          :placeholder="form.auto_title ? autoTitle : '输入赛事名称'"
          :disabled="form.auto_title"
        />
        <view class="switch-row"
          ><text>自动生成标题</text><wd-switch v-model="form.auto_title"
        /></view>
        <text class="field-label">开始日期与时间 *</text
        ><view class="form-two"
          ><picker
            mode="date"
            :value="form.start_date"
            @change="form.start_date = $event.detail.value"
            ><view class="picker-field">{{ form.start_date }}</view></picker
          ><picker
            mode="time"
            :value="form.start"
            @change="form.start = $event.detail.value"
            ><view class="picker-field">{{ form.start }}</view></picker
          ></view
        >
        <text class="field-label">结束日期与时间 *</text
        ><view class="form-two"
          ><picker
            mode="date"
            :value="form.end_date"
            @change="form.end_date = $event.detail.value"
            ><view class="picker-field">{{ form.end_date }}</view></picker
          ><picker
            mode="time"
            :value="form.end"
            @change="form.end = $event.detail.value"
            ><view class="picker-field">{{ form.end }}</view></picker
          ></view
        >
        <text class="field-label">比赛地点 *</text
        ><wd-input
          v-model="form.address"
          placeholder="填写地址，或关联已预订场地"
        />
        <wd-button
          block
          variant="plain"
          @click="
            uni.navigateTo({
              url:
                '/pages/booking/venue-detail?id=' +
                clubs[clubIndex]?.id +
                '&return_mode=tournament',
            })
          "
          >{{ linked ? "已关联场地" : "预订并关联场地" }}</wd-button
        >
        <text class="muted">比赛排场名称不会自动预订场地</text></view
      >
      <wd-collapse v-model="panels">
        <wd-collapse-item name="details" title="更多基础信息 · 介绍、奖项、图片"
          ><view id="details">
            <text class="field-label">赛事介绍</text
            ><wd-textarea v-model="form.description" /><text class="muted">{{
              placeholderHint
            }}</text>
            <text class="field-label">奖项</text
            ><wd-input v-model="form.prize" /><text class="field-label"
              >联系人</text
            ><wd-input v-model="form.contact_name" /><text class="field-label"
              >联系电话</text
            ><wd-input v-model="form.contact_phone" type="tel" />
            <text class="field-label"
              >图片 {{ images.length }}/6 · 首张为封面</text
            ><view class="images"
              ><view v-for="(img, i) in images" :key="img"
                ><Photo :src="img" width="90px" height="90px" /><wd-button
                  size="small"
                  variant="plain"
                  @click="images.splice(i, 1)"
                  >移除</wd-button
                ><wd-button
                  v-if="i"
                  size="small"
                  variant="plain"
                  @click="images.unshift(...images.splice(i, 1))"
                  >设封面</wd-button
                ></view
              ></view
            ><wd-button v-if="images.length < 6" variant="plain" @click="pick"
              >添加图片</wd-button
            >
          </view></wd-collapse-item
        >
      </wd-collapse>
      <text class="section-title">比赛设置</text
      ><text class="muted">{{ summary }}</text
      ><text class="field-label">赛制</text
      ><view class="choices"
        ><wd-button
          v-for="(label, key) in formatNames"
          :key="key"
          size="small"
          :variant="cfg.format === key ? 'base' : 'plain'"
          @click="
            cfg.format = key;
            cfg.allow_draw = false;
          "
          >{{ label }}</wd-button
        ></view
      >
      <text class="field-label">比赛项目</text
      ><view class="choices"
        ><wd-button
          v-for="(label, key) in disciplineNames"
          :key="key"
          size="small"
          :variant="cfg.discipline === key ? 'base' : 'plain'"
          @click="cfg.discipline = key"
          >{{ label }}</wd-button
        ></view
      >
      <text class="field-label">人数上限（个人） *</text
      ><wd-input v-model="form.max_participants" type="number" /><text
        class="field-label"
        >报名费（每人）</text
      ><wd-input v-model="form.entry_fee" type="digit" /><text class="muted"
        >线上预付需经支付退款验收后启用</text
      >
      <text class="field-label">分组数量</text
      ><wd-input v-model="cfg.group_count" type="number" /><text
        class="field-label"
        >场地名称（每行一个）</text
      ><wd-textarea v-model="form.courts" /><text class="field-label"
        >每场预计分钟</text
      ><wd-input v-model="cfg.match_minutes" type="number" />
      <wd-collapse v-model="panels">
        <wd-collapse-item
          name="advanced"
          :title="
            '报名高级设置 · ' +
            (cfg.approval_required ? '需审核' : '免审核') +
            ' · ' +
            (cfg.waitlist_enabled ? '开启候补' : '无候补')
          "
          ><view id="advanced">
            <view class="switch-row"
              ><text>报名需要审核</text
              ><wd-switch v-model="cfg.approval_required" /></view
            ><view class="switch-row"
              ><text>开启候补</text
              ><wd-switch v-model="cfg.waitlist_enabled" /></view
            ><view class="switch-row"
              ><text>参与者不分组展示</text
              ><wd-switch v-model="cfg.ungrouped_display"
            /></view>
            <text class="field-label">报名截止（开赛前小时）</text
            ><wd-input v-model="form.registration_hours" type="digit" /><text
              class="field-label"
              >取消截止（开赛前小时）</text
            ><wd-input v-model="form.cancellation_hours" type="digit" /> </view
        ></wd-collapse-item>
        <wd-collapse-item name="rules" title="赛制高级设置"
          ><view id="rules">
            <view v-if="cfg.format !== 'round_robin'" class="switch-row"
              ><text>季军赛</text><wd-switch v-model="cfg.third_place"
            /></view>
            <view v-if="cfg.format !== 'knockout'" class="switch-row"
              ><text>循环赛允许平局</text><wd-switch v-model="cfg.allow_draw"
            /></view>
            <text class="field-label">每轮最多同时场次（留空按场地数）</text
            ><wd-input
              :model-value="cfg.max_parallel || ''"
              type="number"
              @update:model-value="
                cfg.max_parallel = $event ? Number($event) : null
              "
            />
            <template v-if="cfg.format === 'groups_knockout'"
              ><text class="field-label">每组晋级队数</text
              ><wd-input v-model="cfg.qualifiers_per_group" type="number"
            /></template>
            <text class="muted"
              >比分由管理员填写并指定胜者；淘汰赛支持轮空。</text
            >
          </view></wd-collapse-item
        >
      </wd-collapse>
      <view class="publish-action"
        ><wd-button
          block
          variant="plain"
          :loading="loading"
          @click="showPreview"
          >预览赛程</wd-button
        ><wd-button
          block
          :loading="loading"
          :disabled="!clubs.length"
          @click="save"
          >{{ editId ? "保存赛事" : "发布赛事" }}</wd-button
        ></view
      >
    </view>
    <wd-popup
      v-model="previewVisible"
      position="bottom"
      closable
      round
      root-portal
      :safe-area-inset-bottom="true"
      custom-style="height:88vh;"
    >
      <scroll-view scroll-y style="height: 88vh"
        ><TournamentSchedulePreview
          v-if="preview"
          :preview="preview"
          :config="cfg"
      /></scroll-view>
    </wd-popup>
  </AppShell>
</template>
<style scoped>
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
}
.choices,
.images {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.section-title {
  display: block;
  margin: 24px 0 12px;
}
.muted {
  display: block;
  color: #888;
  font-size: 12px;
  margin: 8px 0;
}
.preview-content {
  padding: 24px;
  max-height: 75vh;
  overflow: auto;
}
.warning {
  display: block;
  color: #ad6a00;
  margin: 12px 0;
}
.publish-action {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
