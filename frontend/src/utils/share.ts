/** Moments opens a single-page preview without a login session. */
export function isTimelinePreview(): boolean {
  try { return Number(uni.getLaunchOptionsSync?.().scene) === 1154; }
  catch { return false; }
}

export function enableActivitySharing() {
  // #ifdef MP-WEIXIN
  uni.showShareMenu?.({ menus: ["shareAppMessage", "shareTimeline"] });
  // #endif
}

export function guideToMiniProgram() {
  uni.showModal({ title: "进入小程序报名", content: "请点击页面底部的“前往小程序”，进入后登录即可报名。", showCancel: false });
}

export function guideTimelineShare() {
  uni.showModal({ title: "分享到朋友圈", content: "请点击右上角“…”菜单，选择“分享到朋友圈”。", showCancel: false });
}

export function activityShare(kind: "post" | "tournament", id: string | number, title?: string, image?: string, invite?: string) {
  const query = `id=${encodeURIComponent(id)}${invite ? "&invite=" + encodeURIComponent(invite) : ""}`;
  const imageUrl = image && /^https:\/\//i.test(image) && !/^https:\/\/(tmp|usr|localhost|127\.0\.0\.1)([/:]|$)/i.test(image)
    ? image : "/static/tennis.jpg";
  return { title: invite ? `邀请你成为「${title || "网球比赛"}」的搭档` : title || (kind === "post" ? "一起约球" : "网球比赛"),
    path: `/pages/common/${kind === "post" ? "post" : "tournament"}-detail?${query}`, query, imageUrl };
}
