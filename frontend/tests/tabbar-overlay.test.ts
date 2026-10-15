import { afterEach, expect, it, vi } from "vitest";
import { suspendCustomTabBar } from "../src/utils/tabbar";

afterEach(() => vi.unstubAllGlobals());

it("hides the owning native tab bar and restores it even after the current page changes", () => {
  const owner = { setData: vi.fn() }, other = { setData: vi.fn() };
  let page: any = { $vm: { $scope: { getTabBar: () => owner } } };
  vi.stubGlobal("getCurrentPages", () => [page]);
  const restore = suspendCustomTabBar();
  expect(owner.setData).toHaveBeenCalledWith({ hidden: true });
  page = { getTabBar: () => other };
  restore();
  expect(owner.setData).toHaveBeenLastCalledWith({ hidden: false });
  expect(other.setData).not.toHaveBeenCalled();
});

it("allows city selection on pages without a custom tab bar", () => {
  vi.stubGlobal("getCurrentPages", () => [{}]);
  expect(() => suspendCustomTabBar()()).not.toThrow();
});
