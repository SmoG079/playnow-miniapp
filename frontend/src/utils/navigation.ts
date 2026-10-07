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
