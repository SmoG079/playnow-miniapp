/** Native custom tab bars render above page popups; suspend the owning instance. */
export function suspendCustomTabBar(): () => void {
  // #ifdef MP-WEIXIN
  if (typeof getCurrentPages === "function") {
    const pages = getCurrentPages();
    const page = pages[pages.length - 1] as any;
    const tabBar = (page?.$vm?.$scope || page)?.getTabBar?.();
    if (tabBar) {
      tabBar.setData({ hidden: true });
      return () => tabBar.setData({ hidden: false });
    }
  }
  // #endif
  return () => {};
}

/** Share the unread count with each WeChat custom tab bar instance. */
export function syncCustomTabBarUnread(count: number) {
  // #ifdef MP-WEIXIN
  if (typeof getApp !== "function" || typeof getCurrentPages !== "function") return;
  const app = getApp();
  if (!app) return;
  app.globalData ||= {};
  app.globalData.playnowUnread = count;
  const pages = getCurrentPages();
  const page = pages[pages.length - 1] as any;
  const nativePage = page?.$vm?.$scope || page;
  nativePage?.getTabBar?.()?.setData({ unread: count > 99 ? "99+" : count ? String(count) : "" });
  // #endif
}

/** Each page updates its own native tab bar before starting asynchronous work. */
export function syncCustomTabBarSelection(active: string | undefined, owner: any) {
  // #ifdef MP-WEIXIN
  const routes = ["home", "clubs", "publish", "chat", "profile"];
  const paths = ["pages/home/index", "pages/booking/club-list", "pages/publish/index", "pages/chat/index", "pages/profile/index"];
  const selected = routes.indexOf(active || "");
  if (selected < 0 || typeof getApp !== "function") return;
  const app = getApp();
  app.globalData ||= {};
  app.globalData.playnowTabPath = paths[selected];
  owner?.getTabBar?.()?.setData({ selected });
  // #endif
}
