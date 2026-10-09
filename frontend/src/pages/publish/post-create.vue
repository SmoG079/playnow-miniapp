<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { onShow, onHide, onUnload } from "@dcloudio/uni-app";
import { chooseUploadedImages, uploadedImage } from "../../services/media";
import AppShell from "../../components/AppShell.vue";
import ActivityLocationSelect from "../../components/ActivityLocationSelect.vue";
import { useDiscovery } from "../../stores/discovery";
import ActivityCoverUpload from "../../components/ActivityCoverUpload.vue";
import { listAll, request } from "../../services/api";
import { useSession } from "../../stores/session";
import { businessDate } from "../../utils/date";
import { saveActivityDraft, readActivityDraft, clearActivityDraft } from "../../services/activity-draft";
const discovery = useDiscovery();
const s = useSession(),
  loading = ref(false),
  coverUploading = ref(false),
  locationSelecting = ref(false),
  statusBarHeight = ref(0),
  editingPost = ref(false),
  showPostComparison = ref(false),
  choosingVenue = ref(false),
  venueName = ref(""),
  clubs = ref<any[]>([]),
  clubIndex = ref(-1),
  images = ref<string[]>([]);
const draftReady = ref(false);
const tournamentDisabledReason = computed(() => "请先登录后创建比赛");
const today = () => businessDate();
const defaultForm = () => ({
  city: discovery.city,
  address: "",
  latitude: null, longitude: null,
  title: "",
  preferred_date: today(),
  preferred_start: "19:00",
  preferred_end: "21:00",
  players_needed: 1,
  price: "0",
  level_required: "",
  description: "",
  notes: "",
  approval_required: false,
  venue_id: null,
  booking_id: null,
});
const form = reactive<any>(defaultForm());
let initialized = false, completed = false, draftOwner = "";
function cacheDraft() {
  if (!initialized || completed || !editingPost.value || !draftOwner || s.user?.id !== draftOwner) return false;
  return saveActivityDraft("post", draftOwner, 0, { form, images: images.value,
    club: clubs.value[clubIndex.value] || null, choosingVenue: choosingVenue.value, venueName: venueName.value });
}
function saveDraft() {
  const saved = cacheDraft();
  uni.showToast({ title: saved ? "草稿已保存，可退出后继续填写" : "草稿保存失败，请重试", icon: "none" });
}
onHide(cacheDraft); onUnload(cacheDraft);
watch([form, images, clubIndex, choosingVenue, venueName, editingPost], cacheDraft, { deep: true, flush: "sync" });
onShow(async () => {
  draftReady.value = false;
  statusBarHeight.value = uni.getWindowInfo().statusBarHeight || 0;
  if (!s.requireLogin("/pages/publish/post-create")) return;
  await s.fetchUser().catch(() => {});
  if (!s.user?.id) return;
  if (draftOwner !== s.user.id || completed) {
    initialized = false; completed = false; draftOwner = s.user.id;
    Object.assign(form, defaultForm()); images.value = []; clubs.value = []; clubIndex.value = -1;
    choosingVenue.value = false; venueName.value = ""; editingPost.value = false;
  }
  await discovery.ensureCity().catch(() => {});
  if (!initialized) {
    const draft = readActivityDraft("post", draftOwner, 0);
    if (draft) {
      Object.assign(form, draft.form); images.value = draft.images || [];
      choosingVenue.value = !!draft.choosingVenue; venueName.value = draft.venueName || "";
      if (draft.club) { clubs.value = [draft.club]; clubIndex.value = 0; }
      editingPost.value = true;
    } else form.city = discovery.city;
  }
  const linked = uni.getStorageSync("booking_return");
  if (linked) {
    form.city = linked.city || form.city;
  }
  await loadClubs();
  if (linked) {
    if (linked.club_id)
      clubIndex.value = clubs.value.findIndex((c) => c.id === Number(linked.club_id));
    editingPost.value = true;
    choosingVenue.value = true;
    venueName.value = linked.venue_name || "已预订场地";
    Object.assign(form, {
      city: linked.city || "", address: linked.address || "", latitude: linked.latitude ?? null, longitude: linked.longitude ?? null,
      venue_id: linked.venue_id,
      booking_id: linked.booking_id,
      preferred_date: linked.slot_date,
      preferred_start: String(linked.slot_start).slice(0, 5),
      preferred_end: String(linked.slot_end).slice(0, 5),
    });
    uni.removeStorageSync("booking_return");
  }
  initialized = true;
  draftReady.value = true;
  cacheDraft();
});
watch(() => discovery.city, value => {
  if (initialized && !form.booking_id && form.city !== value) {
    form.city = value; changeCity();
  }
}, { flush: "sync" });
let clubLoadVersion = 0;
async function loadClubs() {
  const version = ++clubLoadVersion;
  const selected = clubs.value[clubIndex.value]?.id;
  try {
    const available = form.city ? await listAll<any>(`/clubs?city=${encodeURIComponent(form.city)}`) : [];
    if (version !== clubLoadVersion) return;
    clubs.value = available;
    clubIndex.value = clubs.value.findIndex(c => c.id === selected);
  } catch (error: any) {
    if (version !== clubLoadVersion) return;
    clubs.value = []; clubIndex.value = -1;
    uni.showToast({ title: error.message || "球场列表加载失败", icon: "none" });
  }
}
function changeCity() {
  form.address = ""; form.latitude = null; form.longitude = null;
  clubIndex.value = -1; loadClubs();
}
function selectLocation(point: any) {
  Object.assign(form, point); loadClubs();
}
function goClub() {
  if (s.requireLogin("/pages/publish/club-create")) uni.navigateTo({ url: "/pages/publish/club-create" });
}
function goPost() {
  if (!draftReady.value) return;
  editingPost.value = true;
}
function unlinkVenue() {
  form.booking_id = null;
  form.venue_id = null;
  venueName.value = "";
  clubIndex.value = -1;
  choosingVenue.value = false;
  form.address = ""; form.latitude = null; form.longitude = null;
}
async function goTournament() {
  const redirect = "/pages/publish/tournament-create";
  if (!s.requireLogin(redirect)) return;
  uni.navigateTo({ url: redirect });
}

async function pickImages() {
  if (loading.value || coverUploading.value) return;
  coverUploading.value = true;
  try { await chooseUploadedImages(6 - images.value.length, "post", url => { images.value.push(url); }); }
  catch (error: any) { uni.showToast({ title: error.message || "图片上传失败，请重试", icon: "none" }); }
  finally { coverUploading.value = false; }
}
async function submit() {
  if (!draftReady.value || loading.value || coverUploading.value || locationSelecting.value) return;
  if (!form.title.trim())
    return uni.showToast({ title: "请输入标题", icon: "none" });
  if (!form.preferred_date || !form.preferred_start || !form.preferred_end)
    return uni.showToast({ title: "请选择日期和时间", icon: "none" });
  if (form.preferred_end <= form.preferred_start)
    return uni.showToast({ title: "结束时间必须晚于开始时间", icon: "none" });
  if (
    !Number.isInteger(Number(form.players_needed)) ||
    Number(form.players_needed) < 1
  )
    return uni.showToast({ title: "人数至少为 1", icon: "none" });
  if (Number(form.price) < 0 || !Number.isFinite(Number(form.price)))
    return uni.showToast({ title: "请填写有效费用", icon: "none" });
  if (choosingVenue.value && (clubIndex.value < 0 || !form.booking_id))
    return uni.showToast({ title: "请选择俱乐部并完成订场", icon: "none" });
  if (!form.city || (!form.booking_id && (!form.address || form.latitude === null || form.longitude === null))) return uni.showToast({ title: "请在地图中选择活动地点", icon: "none" });
  loading.value = true;
  try {
    const urls = [];
    for (const path of images.value)
      urls.push(
        await uploadedImage(path, "post"),
      );
    await request("/posts", {
      method: "POST",
      data: {
        ...form,
        city: form.city,
        club_id: form.booking_id ? clubs.value[clubIndex.value]?.id : null,
        venue_id: form.booking_id ? form.venue_id : null,
        booking_id: form.booking_id || null,
        price: Number(form.price),
        players_needed: Number(form.players_needed),
        level_required: form.level_required || null,
        images: urls.length ? urls : null,
      },
    });
    completed = true;
    clearActivityDraft("post", draftOwner, 0);
    uni.showToast({ title: "发布成功", icon: "success" });
    setTimeout(() => uni.switchTab({ url: "/pages/home/index" }), 800);
  } catch (e: any) {
    uni.showToast({ title: e.message || "发布失败", icon: "none" });
  } finally {
    loading.value = false;
  }
}
function chooseClub(e: any) {
  clubIndex.value = Number(e.detail.value);
  form.booking_id = null;
  form.venue_id = null;
  venueName.value = "";
}
function goBook() {
  if (clubIndex.value < 0)
    return uni.showToast({ title: "请先选择俱乐部", icon: "none" });
  uni.navigateTo({
    url: `/pages/booking/venue-detail?id=${clubs.value[clubIndex.value].id}&return_mode=post`,
  });
}
</script>
<template>
  <AppShell active="publish"
    ><view
      class="content publish-content"
      :class="{ 'entry-content': !editingPost }"
      ><view
        class="page-heading"
        :style="{ paddingTop: `${26 + statusBarHeight}px` }"
        ><text class="eyebrow">MAKE THE NEXT GAME</text
        ><text class="page-title">好球局，由你发起</text></view
      ><view v-if="!editingPost" class="publish-entries">
        <view class="publish-entry post-entry">
          <view class="entry-heading"
            ><text class="entry-title">发布约球</text
            ><text class="entry-kind">日常约球</text></view
          >
          <text class="entry-description">找球友一起练球、打友谊局。</text>
          <view class="entry-action"
            ><wd-button variant="plain" :disabled="!draftReady" @click="goPost"
              >创建约球</wd-button
            ></view
          >
        </view>
        <view class="publish-entry tournament-entry">
          <view class="entry-heading"
            ><text class="entry-title">发布比赛</text
            ><text class="entry-kind">正式比赛</text></view
          >
          <text class="entry-description"
            >设置赛制，管理报名、抽签和晋级。</text
          >
          <view class="entry-action"
            ><wd-button
              variant="plain"
              :disabled="!s.canPublishTournament"
              @click="goTournament"
              >创建比赛</wd-button
            >
            <text v-if="!s.canPublishTournament" class="permission-note">{{
              tournamentDisabledReason
            }}</text>
          </view>
        </view>
      </view>
      <view v-if="!editingPost" class="create-club-entry"><wd-button variant="text" size="small" custom-style="color:#147553;font-size:13px" @click="goClub">创建俱乐部</wd-button></view>
      <view v-else class="post-form">
        <wd-button variant="text" @click="editingPost = false"
          >返回发布入口</wd-button
        >
        <ActivityCoverUpload v-model="images" :disabled="loading || coverUploading" @busy="coverUploading = $event" />
        <text class="form-title">发布约球</text>
        <text class="muted">场地可选，未关联即为自由约球。</text>
        <text class="field-label">标题 *</text
        ><wd-input
          v-model="form.title"
          placeholder="例如：周五下班，一起打双打"
          :maxlength="40"
          clearable
        /><text class="field-label">场地（可选）</text>
        <view class="venue-association">
          <text v-if="form.booking_id" class="linked-venue"
            >{{ venueName }} · {{ form.preferred_date }}
            {{ form.preferred_start }}–{{ form.preferred_end }}</text
          >
          <text v-else class="muted">{{
            choosingVenue
              ? "选择俱乐部并完成订场后关联"
              : "未关联场地 · 自由约球"
          }}</text>
          <wd-button
            v-if="!choosingVenue"
            variant="plain"
            @click="choosingVenue = true"
            >关联场地</wd-button
          >
          <wd-button v-if="choosingVenue" variant="text" @click="unlinkVenue">{{
            form.booking_id ? "移除关联" : "取消关联"
          }}</wd-button>
        </view>
        <template v-if="choosingVenue && clubs.length"
          ><text class="field-label">俱乐部</text
          ><picker
            :range="clubs.map((c) => c.name)"
            :value="clubIndex"
            @change="chooseClub"
            ><view class="picker-field"
              >{{ clubIndex < 0 ? "请选择" : clubs[clubIndex].name
              }}<wd-icon name="arrow-down" /></view></picker
          ><wd-button block variant="plain" @click="goBook">{{
            form.booking_id ? "已关联预约，重新选择" : "去选择并预订场地"
          }}</wd-button></template
        >
        <view v-if="choosingVenue && !clubs.length" class="venue-empty"><text class="muted">{{ form.city ? '当前城市暂无可预订场地' : '请先在地图中选择活动地点' }}</text><wd-button variant="text" size="small" @click="goClub">创建俱乐部</wd-button></view>
        <view class="comparison-help"><wd-button variant="text" size="small" @click="showPostComparison = true">自由约球与定场约球有什么区别？</wd-button></view>
        <text class="field-label">活动地点</text>
        <ActivityLocationSelect field label="活动地点" :city="form.city" :address="form.address" :disabled="!!form.booking_id" @busy="locationSelecting = $event" @select="selectLocation" />
        <text class="field-label">日期</text
        ><picker
          mode="date"
          :value="form.preferred_date"
          @change="form.preferred_date = $event.detail.value"
          ><view class="picker-field">{{ form.preferred_date }}</view></picker
        ><view class="form-two"
          ><view
            ><text class="field-label">开始</text
            ><picker
              mode="time"
              :value="form.preferred_start"
              @change="form.preferred_start = $event.detail.value"
              ><view class="picker-field">{{
                form.preferred_start
              }}</view></picker
            ></view
          ><view
            ><text class="field-label">结束</text
            ><picker
              mode="time"
              :value="form.preferred_end"
              @change="form.preferred_end = $event.detail.value"
              ><view class="picker-field">{{
                form.preferred_end
              }}</view></picker
            ></view
          ></view
        ><text class="field-label">NTRP 要求</text
        ><wd-input
          v-model="form.level_required"
          placeholder="不限，例如 2.5-3.5"
        /><text class="field-label">还需要几人</text
        ><wd-input-number
          v-model="form.players_needed"
          :min="1"
          :max="30"
        /><text class="field-label">人均费用（元）</text
        ><wd-input v-model="form.price" type="digit" /><text class="field-label"
          >活动说明</text
        ><wd-textarea
          v-model="form.description"
          show-word-limit
          :maxlength="1000"
        /><text class="field-label">活动图片 · 首张为封面</text
        ><view class="image-grid"
          ><Photo
            v-for="(img, i) in images"
            :key="img"
            width="72px"
            height="72px"
            :src="img"
            @click="images.splice(i, 1)" /><button
            class="upload-box"
            @click="pickImages"
          >
            <wd-icon name="plus" /></button></view
        ><wd-cell title="报名需要审核"
          ><wd-switch v-model="form.approval_required" /></wd-cell
        ><view class="publish-action"
          ><wd-button block variant="plain" :disabled="loading || coverUploading || locationSelecting" @click="saveDraft">保存草稿</wd-button
          ><text class="muted small">草稿保存在当前设备，退出后可继续填写。</text
          ><wd-button block :loading="loading || coverUploading || locationSelecting" @click="submit"
            >发布约球</wd-button
          ></view
        ></view
      ></view
    ><wd-popup
      v-model="showPostComparison"
      position="bottom"
      round
      closable
      root-portal
      safe-area-inset-bottom
    >
      <view class="post-comparison">
        <text class="comparison-title">两种约球，怎么选？</text>
        <text class="comparison-subtitle">是否关联场地，决定约球类型。</text>
        <view class="comparison-table">
          <view class="comparison-row comparison-header"
            ><text>区别</text><text>自由约球</text><text>定场约球</text></view
          >
          <view class="comparison-row"
            ><text>谁能发布</text><text>所有登录用户</text
            ><text>所有登录用户</text></view
          >
          <view class="comparison-row"
            ><text>场地安排</text><text>不关联场地，球友自行商定</text
            ><text>关联俱乐部场地及预约</text></view
          >
          <view class="comparison-row"
            ><text>订场要求</text><text>发布前无需订场</text
            ><text>发布前先完成订场</text></view
          >
        </view>
        <wd-button block variant="plain" @click="showPostComparison = false"
          >知道了</wd-button
        >
      </view>
    </wd-popup>
  </AppShell>
</template>

<style scoped>
.entry-content {
  min-height: calc(100vh - 80px - env(safe-area-inset-bottom));
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
.publish-entries {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 32px;
  margin: auto 0;
  padding: 32px 0 40px;
}
.create-club-entry { text-align:center; padding:8px 0 16px; }
.venue-empty { display:flex; flex-direction:column; align-items:flex-start; gap:8px; padding:12px 0; }
.selected-address { display:block; font-size:14px; line-height:1.6; color:#304238; margin-bottom:12px; }
.linked-location { display:flex; align-items:center; gap:10px; padding:14px; border:1px solid var(--playnow-card-border); border-radius:var(--playnow-card-radius); background:#fff; }
.linked-location > view { flex:1; min-width:0; display:flex; flex-direction:column; gap:5px; font-size:14px; }
.publish-entry {
  padding: 0 8px;
}
.entry-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}
.entry-title {
  font-size: 23px;
  font-weight: 600;
  color: #20362c;
}
.entry-kind {
  font-size: 11px;
  color: #547363;
  background: #eaf2ed;
  padding: 4px 8px;
  border-radius: 6px;
}
.entry-description {
  display: block;
  font-size: 13px;
  line-height: 1.7;
  color: #728178;
  margin: 8px 0 14px;
}
.entry-action {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
}
.permission-note {
  font-size: 11px;
  line-height: 1.6;
  color: #728178;
  flex: 1;
}
.form-title {
  display: block;
  margin: 16px 0 8px;
  font-size: 22px;
  font-weight: 600;
}
.venue-association {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.linked-venue {
  font-size: 14px;
}
.comparison-help {
  margin: 8px 0;
}
.post-comparison {
  --wot-button-primary-color: #147553;
  --wot-button-primary-plain-border: #147553;
  padding: 28px 20px 24px;
}
.comparison-title {
  display: block;
  font-size: 21px;
  font-weight: 600;
  padding-right: 28px;
}
.comparison-subtitle {
  display: block;
  margin: 8px 0 20px;
  font-size: 13px;
  color: #728178;
}
.comparison-table {
  border: 1px solid #e2e9e4;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 24px;
}
.comparison-row {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr) minmax(0, 1fr);
  font-size: 12px;
  line-height: 1.7;
}
.comparison-row + .comparison-row {
  border-top: 1px solid #e2e9e4;
}
.comparison-row text {
  padding: 12px 10px;
  color: #566b5e;
}
.comparison-row text + text {
  border-left: 1px solid #e2e9e4;
}
.comparison-header {
  background: #edf5ef;
  font-weight: 600;
}
.comparison-header text {
  color: #284d39;
}
</style>
