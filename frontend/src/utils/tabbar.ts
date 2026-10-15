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
