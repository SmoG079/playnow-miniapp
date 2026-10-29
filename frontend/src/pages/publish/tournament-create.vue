<script setup lang="ts">
import ChoiceSelect from "../../components/ChoiceSelect.vue";
import ChoiceSheet from "../../components/ChoiceSheet.vue";
import ActivityPaymentSelect from "../../components/ActivityPaymentSelect.vue";
import type { PaymentMethod } from "../../domain/activity-payment";
import FieldHelp from "../../components/FieldHelp.vue";
import { normalizedPrizes, type Prize } from "../../domain/prizes";
import { reactive, ref, watch, computed, nextTick } from "vue";
import { onLoad, onShow, onHide, onUnload } from "@dcloudio/uni-app";
import { chooseUploadedImages, uploadedImage } from "../../services/media";
import AppShell from "../../components/AppShell.vue";
import ActivityLocationSelect from "../../components/ActivityLocationSelect.vue";
import { useDiscovery } from "../../stores/discovery";
import ActivityCoverUpload from "../../components/ActivityCoverUpload.vue";
import TournamentSchedulePreview from "../../components/TournamentSchedulePreview.vue";
import { listAll, request } from "../../services/api";
import { useSession } from "../../stores/session";
import {
  defaultConfig,
  formatNames,
  disciplineNames,
  localTime,
  getTournament,
  saveTournament,
} from "../../services/tournaments";
import { tournamentFieldIssues, type TournamentFieldIssue } from "../../domain/tournament-form";
import { buildSchedulePreview } from "../../services/tournament-preview";
import { saveTournamentDraft, readTournamentDraft, clearTournamentDraft } from "../../services/tournament-draft";
import { activitySchedule, freshActivitySchedule } from "../../utils/date";
const discovery = useDiscovery();
const session = useSession(),
  clubs = ref<any[]>([]),
  clubIndex = ref(-1),
  loading = ref(false),
  coverUploading = ref(false),
  locationSelecting = ref(false),
  editId = ref(0),
  panels = ref<string[]>([]),
  images = ref<string[]>([]),
  preview = ref<any>(null),
  previewVisible = ref(false),
  linked = ref<any>(null);
const clubSheet = ref(false), clubLoading = ref(false), clubPurpose = ref("host");
async function chooseClub(purpose = "host") {
  if (clubLoading.value || (purpose === "host" && editId.value)) return;
  clubPurpose.value = purpose;
  clubLoading.value = true;
  const selected = clubs.value[clubIndex.value];
  try {
    const available = await listAll<any>(`/clubs?city=${encodeURIComponent(form.city)}`);
    if (selected && !available.some(c => c.id === selected.id)) available.unshift(selected);
    clubs.value = available;
    clubIndex.value = selected ? clubs.value.findIndex(c => c.id === selected.id) : -1;
    clubSheet.value = true;
  } catch (error:any) { uni.showToast({title:error.message || "俱乐部加载失败",icon:"none"}); }
  finally { clubLoading.value = false; }
}
function selectClub({index}: {index:number}) {
  if (clubPurpose.value === "host") clubIndex.value = index - 1;
  else {
    const club = clubs.value[index];
    if (club) uni.navigateTo({url:`/pages/booking/venue-detail?id=${club.id}&return_mode=tournament`});
  }
  clubSheet.value = false;
}
const clubActions = computed(() => clubPurpose.value === "host" ? [{name:"不设置主办俱乐部"},...clubs.value.map(c => ({name:c.name}))] : clubs.value.map(c => ({name:c.name})));
let initialized = false, completed = false, draftOwner = "";
const draftReady = ref(false);
let pendingBooking: any = null;
function cacheDraft() {
  if (!initialized || completed || !draftOwner || session.user?.id !== draftOwner) return false;
  return saveTournamentDraft(draftOwner, editId.value, { form, config: cfg, images: images.value, club: clubs.value[clubIndex.value] || null, linked: linked.value, panels: panels.value });
}
function saveDraft() {
  const saved = cacheDraft();
  uni.showToast({ title: saved ? "草稿已保存，可退出后继续填写" : "草稿保存失败，请重试", icon: "none" });
}
const cfg = reactive(defaultConfig());
onHide(cacheDraft); onUnload(cacheDraft);
const form = reactive({
  city: discovery.city,
  latitude: null as number | null, longitude: null as number | null,
  title: "",
  auto_title: false,
  ...activitySchedule(),
  entry_fee: "0",
  payment_method: "offline" as PaymentMethod,
  max_participants: 16,
  description:
    "欢迎参加我们的网球比赛！\n时间：{{日期}} {{时间}}\n地点：{{地点}}",

  level_required: "",
  prizes: [] as Prize[],
  address: "",
  location_name: "",
  contact_name: "",
  contact_phone: "",
  registration_hours: "0",
  cancellation_hours: "1",
  courts: "1号场地",
});
const fieldIssues = ref<TournamentFieldIssue[]>([]);
let validatedPreviewOnly = false;
watch([form,cfg,linked], () => { if (fieldIssues.value.length) fieldIssues.value = tournamentFieldIssues(form,cfg,linked.value,validatedPreviewOnly); }, {deep:true});
async function locateIssue(issue:TournamentFieldIssue) {
  if (["advanced","rules"].includes(issue.panel)) panels.value=[...new Set([...panels.value,issue.panel])];
  await nextTick();
  const target = ({start:"start_date",end:"end_date"} as Record<string,string>)[issue.field] || issue.field;
  setTimeout(() => uni.pageScrollTo({selector:"#required-"+target,duration:200}),250);
}
const placeholderHint =
  "支持日期、时间、地点占位符：" +
  ["日期", "时间", "地点"].map((x) => "{{" + x + "}}").join(" ");
const autoTitle = computed(
  () => `${form.start_date} ${disciplineNames[cfg.discipline]}比赛`,
);
watch([form, cfg, images, linked, clubIndex, panels], cacheDraft, { deep:true, flush:"sync" });
onLoad(async (q) => {
  const redirect =
    "/pages/publish/tournament-create" + (q?.id ? `?id=${q.id}` : "");
  if (!session.requireLogin(redirect)) return;
  await session.fetchUser();
  editId.value = Number(q?.id || 0);
  draftOwner = session.user?.id || "";
  const draft = readTournamentDraft(draftOwner, editId.value);
  if (draft) {
    Object.assign(form, draft.form); Object.assign(cfg, draft.config);
    if (!editId.value) Object.assign(form, freshActivitySchedule(form));
    images.value = draft.images || []; linked.value = draft.linked || null; panels.value = draft.panels || [];
    if (draft.club) { clubs.value = [draft.club]; clubIndex.value = 0; }
    initialized = true;
    draftReady.value = true;
    applyReturnedBooking();
    return;
  }
  await discovery.ensureCity().catch(() => {});
  form.city = discovery.city;
  if (!editId.value && session.user?.managed_club_ids?.length) {
    try {
      const club = await request<any>(`/clubs/${session.user.managed_club_ids[0]}`);
      clubs.value = [club]; clubIndex.value = 0;
    } catch { uni.showToast({title:"默认俱乐部加载失败，可点击重新选择",icon:"none"}); }
  }
  Object.assign(form, activitySchedule());
  editId.value = Number(q?.id || 0);
  if (editId.value) {
    const t = await getTournament(editId.value);
    if (t.club_id) {
      const club = await request<any>(`/clubs/${t.club_id}`);
      clubs.value = [club]; clubIndex.value = 0;
    }
    const start = localTime(t.start_time),
      end = localTime(t.end_time);
    Object.assign(form, {
      prizes: t.prizes,
      level_required: t.level_required || "",
      title: t.title,
      auto_title: t.auto_title,
      start_date: start.slice(0, 10),
      end_date: end.slice(0, 10),
      start: start.slice(11),
      end: end.slice(11),
      entry_fee: String(t.entry_fee),
      payment_method: t.payment_method || "online",
      max_participants: t.max_participants,
      description: t.description_template || t.description,

      city: t.city || discovery.city,
      latitude: t.latitude ?? null, longitude: t.longitude ?? null,
      address: t.address || "",
      location_name: t.location_name,
      contact_name: t.contact_name || "",
      contact_phone: t.contact_phone || "",
    });
    if (t.venue_id) linked.value = { venue_id: t.venue_id, venue_name: t.location_name };
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
  initialized = true;
  draftReady.value = true;
  applyReturnedBooking();
});
function applyReturnedBooking() {
  if (!initialized) return;
  const x = pendingBooking || uni.getStorageSync("booking_return");
  if (x) {
    linked.value = x;
    form.city = x.city || ""; form.latitude = x.latitude ?? null; form.longitude = x.longitude ?? null;
    form.address = x.address || "";
    form.location_name = x.venue_name || "";
    pendingBooking = null;
    uni.removeStorageSync("booking_return");
    cacheDraft();
  }
}
onShow(() => {
  if (initialized && !editId.value) Object.assign(form, freshActivitySchedule(form));
  pendingBooking = uni.getStorageSync("booking_return") || pendingBooking; applyReturnedBooking();
});
watch(() => discovery.city, value => {
  if (!editId.value && !linked.value?.venue_id && form.city !== value) {
    form.city = value; form.address = ""; form.location_name = ""; form.latitude = null; form.longitude = null;

  }
}, { flush: "sync" });
function fail(message: string, panel = "advanced") {
  panels.value = [...new Set([...panels.value, panel])];
  uni.showToast({ title: message, icon: "none" });
  uni.pageScrollTo({ selector: "#" + panel, duration: 200 });
}
function payload(previewOnly = false) {
  const prizes=normalizedPrizes(form.prizes);
  if(prizes.some(p=>!p.name)) { panels.value=[...new Set([...panels.value,"prizes"])];uni.showToast({title:"请填写奖项名称",icon:"none"});return; }
  validatedPreviewOnly = previewOnly;
  fieldIssues.value = tournamentFieldIssues(form,cfg,linked.value,previewOnly);
  if (fieldIssues.value.length) {
    panels.value = [...new Set([...panels.value,...fieldIssues.value.map(issue=>issue.panel).filter(panel=>["advanced","rules"].includes(panel))])];
    const first = fieldIssues.value[0];
    uni.showModal({title:"请补充或修改以下信息",content:fieldIssues.value.map(issue=>"· "+issue.message).join("\n"),showCancel:false,confirmText:"去填写",success:()=>void locateIssue(first)});
    return;
  }
  cfg.group_count = Number(cfg.group_count);
  cfg.match_minutes = Number(cfg.match_minutes);
  cfg.qualifiers_per_group = Number(cfg.qualifiers_per_group);
  cfg.max_parallel = cfg.max_parallel == null || String(cfg.max_parallel).trim() === "" ? null : Number(cfg.max_parallel);
  cfg.courts = form.courts.split("\n").map(x=>x.trim()).filter(Boolean);
  if (cfg.format === "knockout") cfg.allow_draw = false;
  const title = form.auto_title ? autoTitle.value : form.title.trim();
  const start = new Date(`${form.start_date}T${form.start}:00+08:00`), end = new Date(`${form.end_date}T${form.end}:00+08:00`);
  return {
    city: form.city,
    latitude: form.latitude, longitude: form.longitude,
    club_id: clubs.value[clubIndex.value]?.id || null,
    title,
    auto_title: form.auto_title,
    sport_type: "网球",
    level_required: form.level_required.trim() || null,
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    entry_fee: Number(form.entry_fee),
    payment_method: form.payment_method,
    max_participants: Number(form.max_participants),
    description: form.description,

    prizes: normalizedPrizes(form.prizes),
    address: form.address,
    location_name: form.location_name,
    contact_name: form.contact_name,
    contact_phone: clubs.value[clubIndex.value]?.id ? form.contact_phone : "",
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
async function pick() {
  if (loading.value || coverUploading.value) return;
  coverUploading.value = true;
  try { await chooseUploadedImages(6 - images.value.length, "post", url => { images.value.push(url); }); }
  catch (error: any) { uni.showToast({ title: error.message || "图片上传失败，请重试", icon: "none" }); }
  finally { coverUploading.value = false; }
}
async function save() {
  if (loading.value || coverUploading.value || locationSelecting.value) return;
  const data = payload();
  if (!data) return;
  loading.value = true;
  try {
    for (const img of images.value)
      data.images.push(
        await uploadedImage(img, "post"),
      );
    const t = await saveTournament(data, editId.value);
    completed = true; clearTournamentDraft(draftOwner, editId.value);
    uni.redirectTo({ url: `/pages/common/tournament-detail?id=${t.id}` });
  } catch (error:any) {
    cacheDraft();
    uni.showToast({title:error.message || "比赛保存失败，请重试",icon:"none"});
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <AppShell back :title="editId ? '编辑赛事' : '创建赛事'"
    ><view class="content publish-content creation-form">
      <ActivityCoverUpload v-model="images" :disabled="loading || coverUploading" @busy="coverUploading = $event" />
      <view v-if="fieldIssues.length" class="validation-summary"><view class="strong">请补充或修改以下信息</view><view v-for="issue in fieldIssues" :key="issue.field" class="validation-item" @click="locateIssue(issue)">· {{ issue.message }}</view></view>
      <view id="basic" class="creation-section"
        ><view class="creation-heading">基本信息</view
        ><view class="field-label">主办俱乐部（选填）</view>
        <view class="picker-field" @click="chooseClub()"><view>{{ clubLoading ? '正在加载…' : clubs[clubIndex]?.name || '不设置主办俱乐部' }}</view><wd-icon v-if="!editId" name="arrow-down" /></view>
        <view class="field-label" id="required-title">赛事名称 *</view><wd-input
          v-model="form.title"
          :placeholder="form.auto_title ? autoTitle : '输入赛事名称'"
          :disabled="form.auto_title"
        />
        <view class="switch-row"
          ><view>自动生成标题</view><wd-switch v-model="form.auto_title"
        /></view>
        </view><view class="creation-section"><view class="creation-heading">时间与地点</view>
        <view class="field-label" id="required-start_date">开始日期与时间 *</view><view class="form-two"
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
        <view class="field-label" id="required-end_date">结束日期与时间 *</view><view class="form-two"
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
        <view class="field-label" id="required-address">比赛地点 *<FieldHelp title="比赛地点与预订" content="在地图中选择地点仅用于展示地址；关联预订场地需要先完成订场。比赛排场名称不会自动预订场地。" /></view>
        <wd-input v-model="form.location_name" :disabled="!!linked?.venue_id" placeholder="地点名称，例如：某某网球中心" :maxlength="256" /><ActivityLocationSelect field label="比赛地点" :city="form.city" :address="form.address" :location-name="form.location_name" :disabled="!!linked?.venue_id" @busy="locationSelecting = $event" @select="point => Object.assign(form, point)" />
        <wd-button block variant="plain" :disabled="!!linked?.venue_id || clubLoading" @click="chooseClub('booking')">{{ linked?.venue_id ? '已关联场地' : '预订并关联场地' }}</wd-button>
        </view
      >
      <ChoiceSheet v-model="clubSheet" :options="clubActions.map((action,index)=>({label:action.name,value:index}))" :value="clubPurpose === 'host' ? clubIndex + 1 : clubIndex" :title="clubPurpose === 'host' ? '选择主办俱乐部' : '选择预订场地的俱乐部'" @select="selectClub({index:Number($event)})" />
      <view class="creation-section creation-collapse"><wd-collapse v-model="panels">
        <wd-collapse-item name="prizes" :title="`奖项设置（选填） · ${normalizedPrizes(form.prizes).length} 条`">
          <view v-for="(prize,i) in form.prizes" :key="i" class="prize-editor">
            <wd-input v-model="prize.name" :maxlength="64" placeholder="奖项名称，例如冠军" />
            <wd-textarea v-model="prize.description" :maxlength="2000" show-word-limit placeholder="奖励说明，支持多行" custom-textarea-class="prize-textarea" />
            <view class="row"><wd-button size="small" variant="text" :disabled="i===0" @click="[form.prizes[i-1],form.prizes[i]]=[form.prizes[i],form.prizes[i-1]]">上移</wd-button><wd-button size="small" variant="text" :disabled="i===form.prizes.length-1" @click="[form.prizes[i+1],form.prizes[i]]=[form.prizes[i],form.prizes[i+1]]">下移</wd-button><wd-button size="small" variant="text" type="danger" @click="form.prizes.splice(i,1)">删除</wd-button></view>
          </view>
          <wd-button custom-class="add-prize-button" variant="plain" :disabled="form.prizes.length>=20" @click="form.prizes.push({name:'',description:''})">新增奖项</wd-button>
        </wd-collapse-item>
      </wd-collapse></view>
      <view class="creation-section creation-collapse"><wd-collapse v-model="panels">
        <wd-collapse-item name="details" title="更多基础信息 · 介绍、图片"
          ><view id="details">
            <view class="field-label">赛事介绍<FieldHelp title="介绍模板" :content="placeholderHint" /></view
            ><wd-textarea v-model="form.description" />
            <view class="field-label"
              >联系人</view
            ><wd-input v-model="form.contact_name" /><view v-if="clubs[clubIndex]?.id" class="field-label"
              >联系电话<FieldHelp title="联系主办方" content="俱乐部主办使用电话联系；个人主办通过小程序内私信联系，不公开电话号码。" /></view
            ><wd-input v-if="clubs[clubIndex]?.id" v-model="form.contact_phone" type="tel" />
            <view class="field-label"
              >图片 {{ images.length }}/6 · 首张为封面</view
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
      </wd-collapse></view>
      <view class="creation-section"><view class="creation-heading">比赛设置</view
      >
      <ChoiceSelect :model-value="cfg.format" title="赛制" label="赛制 *" :options="[
        {value:'knockout',label:formatNames.knockout,description:'胜者晋级，负者淘汰；适合紧凑赛程。'},
        {value:'round_robin',label:formatNames.round_robin,description:'组内队伍循环交手，按成绩排名。'},
        {value:'groups_knockout',label:formatNames.groups_knockout,description:'先进行小组循环赛，再由晋级队伍参加淘汰赛。'}
      ]" @update:model-value="cfg.format = $event as typeof cfg.format; cfg.allow_draw = false" />
      <ChoiceSelect :model-value="cfg.discipline" title="比赛项目" label="比赛项目 *" :options="[
        {value:'singles',label:disciplineNames.singles,description:'每队一人参加比赛。'},
        {value:'doubles',label:disciplineNames.doubles,description:'每队两人，选择固定或随机搭档。'},
        {value:'mixed',label:disciplineNames.mixed,description:'每队一男一女，选择固定或随机搭档。'}
      ]" @update:model-value="cfg.discipline = $event as typeof cfg.discipline; cfg.pairing = null" />
      <view v-if="cfg.discipline !== 'singles'" id="required-pairing">
        <ChoiceSelect :model-value="cfg.pairing || ''" title="搭档方式" label="搭档方式 *" :options="[
          {value:'fixed',label:'固定搭档',description:'参与者选择队伍空位，自行与球友组队。'},
          {value:'random',label:'随机搭档',description:'报名后由系统安排队伍。'}
        ]" @update:model-value="cfg.pairing = $event as typeof cfg.pairing" />
      </view>
        <view class="field-label" id="required-level_required">NTRP 等级（选填）</view>
        <wd-input v-model="form.level_required" :maxlength="32" placeholder="不限，或填写3.0、3.0-4.0" clearable />
      <view class="field-label" id="required-max_participants">人数上限（个人） *</view><wd-input v-model="form.max_participants" type="number" />
      <ActivityPaymentSelect v-model="form.payment_method" :fee="Number(form.entry_fee)" />
      <view class="field-label"
         id="required-entry_fee">报名费（每人） *<FieldHelp title="报名费用" content="免费比赛无需付款；付费比赛按每位参赛者收取，可选择组织者线下收款或微信线上支付。" /></view><wd-input v-model="form.entry_fee" type="digit" />
      <view class="field-label" id="required-group_count">分组数量 *</view><wd-input v-model="cfg.group_count" type="number" /><view
        class="field-label"
         id="required-courts">场地名称（每行一个） *</view><wd-textarea v-model="form.courts" /><view class="field-label"
         id="required-match_minutes">每场预计分钟 *</view><wd-input v-model="cfg.match_minutes" type="number" />
      </view>
      <view class="creation-section creation-collapse"><wd-collapse v-model="panels">
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
              ><view>报名需要审核<FieldHelp title="报名审核" content="开启后，参赛者须由比赛发起者审核通过。待审核的固定队伍席位会保留，拒绝后释放。" /></view
              ><wd-switch v-model="cfg.approval_required" /></view
            ><view class="switch-row"
              ><view>开启候补<FieldHelp title="候补" content="随机搭档和单打比赛名额满后可以候补，递补后按要求完成付款。固定搭档请选择可用队伍空位。" /></view
              ><wd-switch v-model="cfg.waitlist_enabled" /></view
            ><view class="switch-row"
              ><view>参与者不分组展示</view
              ><wd-switch v-model="cfg.ungrouped_display"
            /></view>
            <view class="field-label" id="required-registration_hours">报名截止（开赛前小时） *</view><wd-input v-model="form.registration_hours" type="digit" /><view
              class="field-label"
               id="required-cancellation_hours">取消截止（开赛前小时） *</view><wd-input v-model="form.cancellation_hours" type="digit" /> </view
        ></wd-collapse-item>
        <wd-collapse-item name="rules" title="赛制高级设置"
          ><view id="rules">
            <view v-if="cfg.format !== 'round_robin'" class="switch-row"
              ><view>季军赛</view><wd-switch v-model="cfg.third_place"
            /></view>
            <view v-if="cfg.format !== 'knockout'" class="switch-row"
              ><view>循环赛允许平局</view><wd-switch v-model="cfg.allow_draw"
            /></view>
            <view class="field-label" id="required-max_parallel">每轮最多同时场次（留空按场地数）</view><wd-input
              :model-value="cfg.max_parallel || ''"
              type="number"
              @update:model-value="
                cfg.max_parallel = $event ? Number($event) : null
              "
            />
            <template v-if="cfg.format === 'groups_knockout'"
              ><view class="field-label" id="required-qualifiers_per_group">每组晋级队数 *</view><wd-input v-model="cfg.qualifiers_per_group" type="number"
            /></template>
            <view class="creation-label"><view class="field-label">计分与结果</view><FieldHelp title="比赛结果" content="比分由管理员填写并指定胜者；淘汰赛支持轮空。" /></view>
          </view></wd-collapse-item
        >
      </wd-collapse></view>
      <view class="publish-action"
        ><view class="creation-label"><wd-button block variant="plain" :disabled="!draftReady || loading || coverUploading || locationSelecting" @click="saveDraft">保存草稿</wd-button
        ><FieldHelp title="保存草稿" content="草稿保存在当前设备，退出后可继续填写。" /></view><wd-button
          block
          variant="plain"
          :loading="loading || coverUploading || locationSelecting"
          @click="showPreview"
          >预览赛程</wd-button
        ><wd-button
          block
          :loading="loading || coverUploading || locationSelecting"
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
.validation-summary{padding:16px;border:1px solid #e3cda8;border-radius:12px;background:#fffaf1;margin:16px 0}.validation-item{display:block;margin-top:8px;font-size:13px;line-height:1.6;color:#976424}

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

<style scoped>
.prize-editor { margin-bottom:16px; padding:12px; border:1px solid #e5e8e5; border-radius:12px; }
:deep(.prize-textarea) { min-height:140px; }
</style>

<style scoped lang="scss">
@use "../../styles/creation-form.scss";
</style>
