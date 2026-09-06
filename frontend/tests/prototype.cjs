const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const out = path.resolve(process.argv[2] || "artifacts");
fs.mkdirSync(out, { recursive: true });
const base = process.env.PROTOTYPE_URL || "http://127.0.0.1:5188";
const routes = {
  home: "home/index",
  clubs: "booking/club-list",
  venue: "booking/venue-detail?id=1",
  activity: "common/post-detail?id=1",
  publish: "publish/post-create",
  profile: "profile/index",
  chat: "chat/index",
};
(async () => {
  const browser = await chromium.launch({ headless: true, channel: "msedge" });
  const page = await browser.newPage({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
  });
  const errors = [],
    externalRequests = [],
    results = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (/^https?:/.test(r.url()) && !r.url().startsWith(base))
      externalRequests.push(r.url());
  });
  let visitNumber = 0;
  async function visit(name) {
    await page.goto(`${base}/?qa=${++visitNumber}#/pages/${routes[name]}`, {
      waitUntil: "networkidle",
    });
    await page.waitForTimeout(200);
  }
  async function snap(name, full = false) {
    // Anchor persistent controls to the end of long-page review exports only.
    await page.screenshot({
      path: path.join(out, `${name}.png`),
      fullPage: full,
      animations: "disabled",
      style: full
        ? ".app-shell{position:relative!important}.bottom-nav,.fixed-action{position:absolute!important;bottom:0!important}"
        : "",
    });
  }
  try {
    for (const width of [375, 390, 430]) {
      await page.setViewportSize({ width, height: 844 });
      for (const name of Object.keys(routes)) {
        await visit(name);
        assert.equal(await page.locator(".app-shell").count(), 1, name);
        const dimensions = await page.evaluate(() => ({
          w: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
        }));
        assert.ok(
          dimensions.scroll <= dimensions.w + 1,
          `${name} overflows at ${width}`,
        );
        const broken = await page
          .locator("uni-image img")
          .evaluateAll(
            (imgs) =>
              imgs.filter((i) => !i.complete || i.naturalWidth === 0).length,
          );
        assert.equal(broken, 0, `${name}: missing images`);
        if (width === 390 && name !== "chat") await snap(name, true);
        results.push(`${name}@${width}: layout and images pass`);
      }
      await visit("home");
      await page.getByText("全部时间", { exact: false }).click();
      const popup = await page.locator(".prototype-sheet").boundingBox();
      assert.ok(popup && popup.x >= -1 && popup.x + popup.width <= width + 1);
      if (width === 390) await snap("filter");
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await visit("home");
    await page.getByText("全部时间", { exact: false }).click();
    await page
      .locator(".prototype-sheet")
      .getByText("今天", { exact: true })
      .click();
    await page
      .locator(".prototype-sheet")
      .getByText("4.0", { exact: true })
      .click();
    await page.getByText("查看活动", { exact: true }).click();
    await page.getByText("暂时没有合适的活动").waitFor();
    await page.getByText("清除筛选", { exact: true }).click();
    assert.equal(await page.locator(".activity-card").count(), 3);
    await page.getByText("比赛", { exact: true }).click();
    assert.equal(await page.locator(".activity-card").count(), 1);
    results.push("combined filters, reset and tournament switch pass");
    await visit("venue");
    await page.locator(".slot-row").nth(0).locator(".slot").nth(0).click();
    await page.locator(".slot-row").nth(1).locator(".slot").nth(0).click();
    await snap("slots-selected");
    await page.getByText("确认时段", { exact: true }).click();
    await page.waitForTimeout(350);
    await snap("booking-confirm");
    await page.getByText("完成模拟预约", { exact: true }).click();
    await page.getByText("预约已记录，准备上场").waitFor();
    await snap("booking-success");
    await page.getByText("查看我的预约", { exact: true }).click();
    await page.getByText("下一场，已经安排好了").waitFor();
    await page.getByText("我的预约", { exact: true }).click();
    await page.getByText("¥80 · 模拟预约").waitFor();
    results.push(
      "slot selection, booking confirmation and profile record pass",
    );
    await visit("activity");
    await page.getByText("加入这场球", { exact: true }).click();
    await page
      .locator('[role="status"]')
      .getByText("报名成功，球场见！", { exact: false })
      .waitFor();
    await snap("joined");
    results.push("activity join and disabled duplicate join state pass");
    await visit("publish");
    await page.getByText("发布约球", { exact: true }).click();
    await page.getByText("请填写约球标题", { exact: true }).waitFor();
    await page.locator(".wd-input input").first().fill("周五夜场 · 快乐双打");
    await page.locator(".wd-input input").last().fill("50");
    await page.getByText("发布约球", { exact: true }).click();
    await page.getByText("发布成功，已加入约球广场（模拟）").waitFor();
    await page.getByText("去广场看看", { exact: true }).click();
    await page.getByText("周五夜场 · 快乐双打", { exact: true }).waitFor();
    results.push("required validation, publish and shared activity state pass");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await visit("home");
    const box = await page.locator(".app-shell").boundingBox();
    assert.equal(box.width, 430);
    await snap("desktop");
    assert.equal(errors.length, 0, errors.join("\n"));
    assert.equal(externalRequests.length, 0, externalRequests.join("\n"));
    results.push(
      "desktop phone framing, no runtime errors, no external API requests pass",
    );
    fs.writeFileSync(
      path.join(out, "verification.json"),
      JSON.stringify({ results, errors, externalRequests }, null, 2),
    );
    console.log(
      JSON.stringify({ passed: results.length, errors, externalRequests }),
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
