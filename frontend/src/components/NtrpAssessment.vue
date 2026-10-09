<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { loadRatingQuestionnaire, saveRatingAssessment, type RatingQuestionnaire, type RatingResult } from "../services/rating-assessment";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean]; completed: [result: RatingResult] }>();
const open = computed({ get: () => props.modelValue, set: value => { if (!saving.value) emit("update:modelValue", value); } });
const catalog = ref<RatingQuestionnaire | null>(null), loading = ref(false), saving = ref(false), error = ref("");
const mode = ref<"quick" | "full">("quick"), quick = ref<number>(-1), step = ref(0);
const answers = ref<Record<string, number>>({});
const current = computed(() => catalog.value?.questions[step.value]);
const choice = computed({
  get: () => current.value ? answers.value[current.value.id] ?? -1 : -1,
  set: (value: number) => { if (current.value) answers.value[current.value.id] = value; },
});
let loadVersion = 0;
async function load() {
  const version = ++loadVersion;
  loading.value = true; error.value = "";
  try {
    const result = await loadRatingQuestionnaire();
    if (version === loadVersion && props.modelValue) catalog.value = result;
  } catch (e: any) {
    if (version === loadVersion && props.modelValue) error.value = e.message || "问卷加载失败，请重试";
  } finally { if (version === loadVersion) loading.value = false; }
}
watch(() => props.modelValue, value => {
  if (value) {
    mode.value = "quick"; quick.value = -1; step.value = 0; answers.value = {}; catalog.value = null;
    load();
  } else loadVersion++;
});
function fullQuestionnaire() { if (!saving.value) { mode.value = "full"; step.value = 0; } }
async function submit() {
  if (saving.value || !catalog.value) return;
  const values: Record<string, number> = mode.value === "quick" ? { level: quick.value } : { ...answers.value };
  if (mode.value === "quick" ? quick.value < 0 : catalog.value.questions.some(question => values[question.id] === undefined)) return;
  saving.value = true;
  try {
    const result = await saveRatingAssessment(catalog.value.version, mode.value, values);
    emit("completed", result);
    emit("update:modelValue", false);
    uni.showToast({ title: `已保存 NTRP ${Number(result.ntrp_level).toFixed(1)}`, icon: "none" });
  } catch (e: any) {
    uni.showToast({ title: e.message || "定级保存失败，请重试", icon: "none" });
  } finally { saving.value = false; }
}
function next() {
  if (choice.value < 0 || !catalog.value) return;
  if (step.value < catalog.value.questions.length - 1) step.value++;
  else submit();
}
</script>

<template>
  <wd-popup v-model="open" position="bottom" round root-portal :closable="!saving"
    :close-on-click-modal="!saving" :safe-area-inset-bottom="true" custom-style="max-height:90vh;">
    <view class="rating-sheet">
      <view class="rating-handle" />
      <text class="rating-title">网球 · 测测我的等级</text>
      <view v-if="loading" class="rating-loading"><wd-loading /></view>
      <view v-else-if="error" class="rating-loading">
        <text>{{ error }}</text><wd-button variant="plain" @click="load">重新加载</wd-button>
      </view>
      <template v-else-if="catalog">
        <scroll-view scroll-y class="rating-body" :scroll-top="0" :key="mode + '-' + step">
          <text class="rating-notice">{{ catalog.notice }}</text>
          <template v-if="mode === 'quick'">
            <text class="rating-intro">选一档快速定级，或完成问卷细评。</text>
            <wd-radio-group v-model="quick" checked-color="#147553" :disabled="saving">
              <view v-for="level in catalog.quick_levels" :key="level.value" class="rating-card" :class="{ chosen: quick === level.value }">
                <wd-radio :value="level.value" custom-style="display:flex;padding:14px;margin:0;">
                  <view class="rating-level-row">
                    <text class="rating-level">{{ level.value }}</text>
                    <view class="rating-level-copy"><text class="rating-name">{{ level.name }}</text><text class="rating-description">{{ level.description }}</text></view>
                  </view>
                </wd-radio>
              </view>
            </wd-radio-group>
            <wd-button block variant="text" :disabled="saving" @click="fullQuestionnaire">做完整问卷（更细致）</wd-button>
          </template>
          <template v-else-if="current">
            <text class="rating-progress">{{ step + 1 }} / {{ catalog.questions.length }}</text>
            <text class="rating-question">{{ current.title }}</text>
            <wd-radio-group v-model="choice" checked-color="#147553" :disabled="saving">
              <view v-for="option in current.options" :key="option.value" class="rating-card" :class="{ chosen: choice === option.value }">
                <wd-radio :value="option.value" custom-style="display:flex;padding:14px;margin:0;"><text class="rating-description">{{ option.description }}</text></wd-radio>
              </view>
            </wd-radio-group>
          </template>
        </scroll-view>
        <view class="rating-footer">
          <template v-if="mode === 'full'">
            <wd-button variant="plain" :disabled="saving" @click="step ? step-- : mode = 'quick'">{{ step ? '上一题' : '返回选档' }}</wd-button>
            <wd-button :disabled="choice < 0" :loading="saving" @click="next">{{ step === catalog.questions.length - 1 ? '完成并保存' : '下一题' }}</wd-button>
          </template>
          <wd-button v-else block :disabled="quick < 0" :loading="saving" @click="submit">{{ quick < 0 ? '请选择一档' : '确认定级并保存' }}</wd-button>
        </view>
      </template>
    </view>
  </wd-popup>
</template>

<style scoped lang="scss">
.rating-sheet { background: #fff; color: #20362a; }
.rating-handle { width: 38px; height: 4px; margin: 12px auto 20px; border-radius: 4px; background: #dfe5df; }
.rating-title { display: block; padding: 0 24px 18px; font-size: 23px; font-weight: 700; border-bottom: 1px solid #edf0ed; }
.rating-body { height: 58vh; box-sizing: border-box; padding: 18px 22px; }
.rating-loading { display: flex; flex-direction: column; align-items: center; gap: 20px; padding: 45px 24px; }
.rating-notice, .rating-intro { display: block; font-size: 12px; line-height: 1.7; color: #7a867f; margin-bottom: 12px; }
.rating-intro { color: #334e3e; font-size: 14px; }
.rating-card { background: #f3f5f2; border: 1px solid transparent; border-radius: 12px; margin-bottom: 10px; }
.rating-card.chosen { background: #e7f2ea; border-color: #147553; }
.rating-level-row { display: flex; align-items: center; gap: 12px; }
.rating-level { flex-shrink: 0; width: 38px; height: 42px; line-height: 42px; text-align: center; background: #fff; border-radius: 9px; font-size: 25px; font-weight: 700; }
.rating-level-copy { flex: 1; min-width: 0; text-align: left; }
.rating-name { display: block; font-size: 17px; font-weight: 650; margin-bottom: 4px; }
.rating-description { display: block; font-size: 13px; line-height: 1.6; white-space: normal; text-align: left; }
.rating-progress { display: block; color: #147553; font-size: 13px; margin-bottom: 8px; }
.rating-question { display: block; font-size: 19px; font-weight: 650; margin-bottom: 16px; }
.rating-footer { display: flex; justify-content: space-between; gap: 12px; padding: 16px 22px; border-top: 1px solid #edf0ed; }
</style>
