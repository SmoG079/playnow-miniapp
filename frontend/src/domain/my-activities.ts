export function identityLabels(user: { role?: string; roles?: string[]; managed_club_ids?: number[] } | null) {
  const roles = new Set(user?.roles || []);
  if (user?.role) roles.add(user.role);
  if (user?.managed_club_ids?.length) roles.add("club_admin");
  const labels = [];
  if (roles.has("platform_admin")) labels.push("系统管理员");
  if (roles.has("club_admin")) labels.push("俱乐部管理员");
  return labels.length ? labels : ["用户"];
}
export function registrationLabel(item: any): string {
  const r = item.registration;
  if (!r) return "";
  if (["closed", "cancelled"].includes(item.status)) return "活动已关闭";
  if (item.kind === "post") return ({pending:"待审核",approved:"报名成功",rejected:"未通过",cancelled:"已取消"} as Record<string,string>)[r.status] || "报名处理中";
  if (r.approval === "rejected") return "未通过";
  if (["cancelled","expired","rejected"].includes(r.admission)) return r.admission === "expired" ? "名额已过期" : "已取消";
  if (r.approval === "pending") return "待审核";
  if (r.admission === "waitlisted") return "候补中";
  if (r.payment === "pending") return "待支付";
  if (["unverified","abnormal"].includes(r.payment)) return "付款待核验";
  if (r.admission === "active" && r.approval === "approved" && ["none","paid","verified"].includes(r.payment)) return "报名成功";
  return "报名处理中";
}
export function activityQuery(kind: string, relation: string, phase: string, keyword: string, page: number) {
  return `/users/me/activity-records?kind=${kind}&relation=${relation}&phase=${phase}&keyword=${encodeURIComponent(keyword.trim())}&page=${page}&page_size=20`;
}
