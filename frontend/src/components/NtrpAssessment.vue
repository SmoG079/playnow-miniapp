<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ratingQuestionnaire as catalog, assessQuestionnaire, NTRP_LEVELS, NTRP_QUESTIONS } from "../domain/rating-assessment";
import { saveRatingAssessment } from "../services/rating-assessment";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean]; completed: [level: number] }>();
const open = computed({ get: () => props.modelValue, set: value => { if (!saving.value) emit("update:modelValue", value); } });
const saving = ref(false);
const mode = ref<"quick" | "full" | "result">("quick"), quick = ref<number>(-1), step = ref(0);
const answers = ref<Record<string, number>>({});
const current = computed(() => NTRP_QUESTIONS[step.value]);
const result = computed(() => assessQuestionnaire(answers.value));
const formattedRating = computed(() => result.value?.rating.toFixed(1) ?? "");
const choice = computed({
  get: () => current.value ? answers.value[current.value.id] ?? -1 : -1,
  set: (value: number) => { if (current.value) answers.value[current.value.id] = value; },
});
watch(() => props.modelValue, value => {
  if (value) {
    mode.value = "quick";
    quick.value = -1;
    step.value = 0;
    answers.value = {};
  }
});
function fullQuestionnaire() { if (!saving.value) { mode.value = "full"; step.value = 0; } }
async function submit() {
  if (saving.value) return;
  const level = mode.value === "quick"
    ? catalog.quick_levels.find(option => option.value === quick.value)?.value
    : result.value?.rating;
  if (level == null) return;
  saving.value = true;
  try {
    await saveRatingAssessment(level);
    emit("completed", level);
    emit("update:modelValue", false);
    uni.showToast({ title: `已保存 NTRP ${level.toFixed(1)}`, icon: "none" });
  } catch (e: any) {
    uni.showToast({ title: e.message || "定级保存失败，请重试", icon: "none" });
  } finally { saving.value = false; }
}
function next() {
  if (!current.value.options.some(option => option.score === choice.value)) return;
  if (step.value < NTRP_QUESTIONS.length - 1) step.value++;
  else if (result.value) mode.value = "result";
}
</script>

<template>
  <wd-popup v-model="open" position="bottom" round root-portal :closable="!saving"
    :close-on-click-modal="!saving" :safe-area-inset-bottom="true" custom-style="max-height:90vh;">
    <view class="rating-sheet">
      <view class="rating-handle" />
      <text class="rating-title">网球 · 测测我的等级</text>
      <scroll-view scroll-y class="rating-body" :scroll-top="0" :key="mode + '-' + step">
        <text v-if="mode !== 'result'" class="rating-notice">{{ catalog.notice }}</text>
        <template v-if="mode === 'quick'">
          <text class="rating-intro">选一档快速定级，或完成问卷细评。</text>
          <wd-radio-group v-model="quick" checked-color="#147553" :disabled="saving">
            <wd-radio v-for="level in catalog.quick_levels" :key="level.value" :value="level.value" custom-class="rating-card">
              <view class="rating-level-row">
                <text class="rating-level">{{ level.value.toFixed(1) }}</text>
                <view class="rating-level-copy"><text class="rating-name">{{ level.name }}</text><text class="rating-description">{{ level.description }}</text></view>
              </view>
            </wd-radio>
          </wd-radio-group>
          <wd-button block variant="text" :disabled="saving" @click="fullQuestionnaire">做完整问卷（更细致）</wd-button>
        </template>
        <template v-else-if="mode === 'full'">
          <text class="rating-progress">{{ step + 1 }} / {{ NTRP_QUESTIONS.length }}</text>
          <text class="rating-question">{{ current.title }}</text>
          <wd-radio-group v-model="choice" checked-color="#147553" :disabled="saving">
            <wd-radio v-for="option in current.options" :key="current.id + '-' + option.score" :value="option.score" custom-class="rating-card">
              <text class="rating-description">{{ option.label }}</text>
            </wd-radio>
          </wd-radio-group>
        </template>
        <template v-else-if="result">
          <view class="rating-result">
            <text class="rating-progress">自评结果</text>
            <text class="rating-result-score">NTRP {{ formattedRating }}</text>
            <text class="rating-description">{{ NTRP_LEVELS[formattedRating] }}</text>
          </view>
          <text v-if="result.showWeaknessTip" class="rating-weakness">
            最弱的一项是「{{ result.weakestTitle }}」，NTRP 看整体水平，短板会拉低等级。
          </text>
          <text class="rating-notice">本结果为简化自评，非 USTA 官方定级。中国网协技术等级采用 CTN 1–10 级。</text>
        </template>
      </scroll-view>
      <view class="rating-footer">
        <template v-if="mode === 'full'">
          <wd-button variant="plain" :disabled="saving" @click="step ? step-- : mode = 'quick'">{{ step ? '上一题' : '返回选档' }}</wd-button>
          <wd-button :disabled="choice < 0" @click="next">{{ step === NTRP_QUESTIONS.length - 1 ? '查看结果' : '下一题' }}</wd-button>
        </template>
        <template v-else-if="mode === 'result'">
          <wd-button variant="plain" :disabled="saving" @click="mode = 'full'">返回修改</wd-button>
          <wd-button :disabled="!result" :loading="saving" @click="submit">保存等级</wd-button>
        </template>
        <wd-button v-else block :disabled="quick < 0" :loading="saving" @click="submit">{{ quick < 0 ? '请选择一档' : '确认定级并保存' }}</wd-button>
      </view>
    </view>
  </wd-popup>
</template>

<style scoped lang="scss">
.rating-sheet { background: #fff; color: #20362a; }
.rating-handle { width: 38px; height: 4px; margin: 12px auto 20px; border-radius: 4px; background: #dfe5df; }
.rating-title { display: block; padding: 0 24px 18px; font-size: 23px; font-weight: 700; border-bottom: 1px solid #edf0ed; }
.rating-body { height: 58vh; box-sizing: border-box; padding: 18px 22px; }
.rating-notice, .rating-intro { display: block; font-size: 12px; line-height: 1.7; color: #7a867f; margin-bottom: 12px; }
.rating-intro { color: #334e3e; font-size: 14px; }
.rating-sheet :deep(.rating-card) {
  display: flex;
  margin: 0 0 10px;
  padding: 14px;
  background: #f3f5f2;
  border: 1px solid transparent;
  border-radius: 12px;
}
.rating-sheet :deep(.rating-card.is-checked) { background: #e7f2ea; border-color: var(--playnow-brand); }
.rating-level-row { display: flex; align-items: center; gap: 12px; }
.rating-level { flex-shrink: 0; width: 38px; height: 42px; line-height: 42px; text-align: center; background: #fff; border-radius: 9px; font-size: 25px; font-weight: 700; }
.rating-level-copy { flex: 1; min-width: 0; text-align: left; }
.rating-name { display: block; font-size: 17px; font-weight: 650; margin-bottom: 4px; }
.rating-description { display: block; font-size: 13px; line-height: 1.6; white-space: normal; text-align: left; }
.rating-progress { display: block; color: var(--playnow-brand); font-size: 13px; margin-bottom: 8px; }
.rating-question { display: block; font-size: 19px; font-weight: 650; margin-bottom: 16px; }
.rating-result { padding: 20px; margin-bottom: 14px; border-radius: 12px; background: #f3f5f2; }
.rating-result-score { display: block; margin-bottom: 12px; font-size: 32px; font-weight: 700; }
.rating-weakness { display: block; margin-bottom: 14px; font-size: 13px; line-height: 1.6; color: #334e3e; }
.rating-footer { display: flex; justify-content: space-between; gap: 12px; padding: 16px 22px; border-top: 1px solid #edf0ed; }
</style>
