/** Moments opens a single-page preview without a login session. */
export function isTimelinePreview(): boolean {
  try { return Number(uni.getLaunchOptionsSync?.().scene) === 1154; }
  catch { return false; }
}

export function enableActivitySharing(timeline = true) {
  // #ifdef MP-WEIXIN
  uni.showShareMenu?.({ menus: timeline ? ["shareAppMessage", "shareTimeline"] : ["shareAppMessage"] });
  // #endif
}

export function homeShare() {
  return { title: "e球有约 · 网球约球与赛事报名", path: "/pages/home/index", imageUrl: "/static/tennis.jpg" };
}

function shareCover(image?: string) {
  return image && /^https:\/\//i.test(image) && !/^https:\/\/(tmp|usr|localhost|127\.0\.0\.1)([/:]|$)/i.test(image)
    ? image : "/static/tennis.jpg";
}

export function clubShare(id: number, title?: string, image?: string) {
  const query = `id=${encodeURIComponent(id)}`;
  return { title: title || "网球俱乐部", path: `/pages/common/club-detail?${query}`, query, imageUrl: shareCover(image) };
}

export function guideToMiniProgram() {
  uni.showModal({ title: "进入小程序报名", content: "请点击页面底部的“前往小程序”，进入后登录即可报名。", showCancel: false });
}

export function activityShare(kind: "post" | "tournament", id: string | number, title?: string, image?: string, invite?: string) {
  const query = `id=${encodeURIComponent(id)}${invite ? "&invite=" + encodeURIComponent(invite) : ""}`;
  const imageUrl = shareCover(image);
  return { title: invite ? `邀请你成为「${title || "网球比赛"}」的搭档` : title || (kind === "post" ? "一起约球" : "网球比赛"),
    path: `/pages/common/${kind === "post" ? "post" : "tournament"}-detail?${query}`, query, imageUrl };
}
