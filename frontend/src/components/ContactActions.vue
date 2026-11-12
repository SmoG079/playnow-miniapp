<script setup lang="ts">
import { ref } from "vue";
import { request } from "../services/api";
import { useSession } from "../stores/session";

/**
 * Two ways to reach the other side of an activity: an in-app private
 * conversation and a phone call. Icon-only round buttons keep the rows compact,
 * so the caller can drop them into a list without stealing space from actions.
 *
 * For the host of the activity no peer id is required: the backend falls back
 * to the organiser when `target_user_id` is omitted.
 */
const props = defineProps<{
  activityId: number;
  /** Public id of the球友 to message; omit when the viewer is that person. */
  userId?: string | null;
  phone?: string | null;
  /** The buttons reach the host of this activity rather than a named player. */
  organizer?: boolean;
  redirect?: string;
  size?: "small" | "large";
}>();
const session = useSession();
const chatting = ref(false);

function call() {
  if (!props.phone) return;
  uni.makePhoneCall({
    phoneNumber: String(props.phone),
    fail: () => uni.showToast({ title: "暂时无法拨号", icon: "none" }),
  });
}

async function chat() {
  if (!props.userId && !props.organizer) return;
  if (!session.requireLogin(props.redirect)) return;
  if (chatting.value) return;
  chatting.value = true;
  try {
    const data: Record<string, unknown> = { activity_id: props.activityId };
    if (props.userId) data.target_user_id = props.userId;
    const conversation = await request<{ id: string }>("/messages/conversations", {
      method: "POST",
      data,
    });
    uni.navigateTo({ url: "/pages/chat/conversation?id=" + conversation.id });
  } catch (e: any) {
    uni.showToast({ title: e.message || "暂时无法发起消息", icon: "none" });
  } finally {
    chatting.value = false;
  }
}
</script>

<template>
  <view class="contact-actions">
    <button
      v-if="userId || organizer"
      class="contact-action"
      :class="size === 'large' ? 'is-large' : ''"
      :aria-label="organizer ? '私聊主办方' : '私聊该球友'"
      :disabled="chatting"
      @click.stop="chat"
    >
      <wd-icon name="message" size="17px" />
    </button>
    <button
      v-if="phone"
      class="contact-action"
      :class="size === 'large' ? 'is-large' : ''"
      aria-label="拨打电话"
      @click.stop="call"
    >
      <wd-icon name="phone" size="17px" />
    </button>
  </view>
</template>

<style scoped>
.contact-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.contact-action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  min-width: 0;
  min-height: 0;
  margin: 0;
  padding: 0;
  border: 1px solid var(--playnow-brand);
  border-radius: 50%;
  background: var(--playnow-brand-soft);
  color: var(--playnow-brand);
  line-height: 1;
  flex: none;
  overflow: hidden;
}
.contact-action.is-large {
  width: 36px;
  height: 36px;
}
.contact-action::after {
  border: 0;
}
.contact-action[disabled] {
  opacity: 0.5;
}
</style>
