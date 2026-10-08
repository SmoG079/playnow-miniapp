import { TAB_PAGES } from "../config";

export function openPage(url: string) {
  const path = url.split("?")[0];
  if (TAB_PAGES.includes(path)) uni.switchTab({ url: path });
  else uni.navigateTo({ url });
}

export function backOrHome() {
  if (getCurrentPages().length > 1) uni.navigateBack();
  else uni.reLaunch({ url: "/pages/home/index" });
}

/** Return to the existing form instead of creating a second, blank page. */
export function returnToActivityForm(mode: string) {
  const route = mode === "tournament" ? "pages/publish/tournament-create" : "pages/publish/post-create";
  const pages = getCurrentPages();
  const index = pages.map(page => page.route).lastIndexOf(route);
  if (index >= 0 && index < pages.length - 1) return uni.navigateBack({ delta: pages.length - 1 - index });
  if (mode === "post") return uni.switchTab({ url: "/" + route });
  return uni.redirectTo({ url: "/" + route });
}
