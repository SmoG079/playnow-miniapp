// Run against an isolated backend with seeded users, never against the configured production API.
// PLAYWRIGHT_MODULE, RATING_QA_API and RATING_QA_OUTPUT can override local test paths.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.RATING_QA_FRONTEND || "http://127.0.0.1:5188";
const api = process.env.RATING_QA_API || "http://127.0.0.1:18009";
const output = process.env.RATING_QA_OUTPUT || "/tmp/playnow-rating-ui";
for (const url of [base, api]) assert.equal(new URL(url).hostname, "127.0.0.1", "Only isolated localhost test services are allowed");
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const fixture = await context.request.get(api + "/fixture-session");
    assert.equal(fixture.status(), 200);
    const { token } = await fixture.json();
    const productionBase = "https://www.tennisplaynow.site:8443/api/v1";
    const errors = [], requests = [];
    let failSave = false;
    await context.route("**/*", async route => {
      const request = route.request(), url = request.url();
      if (url.startsWith(productionBase + "/")) {
        const headers = { "access-control-allow-origin": base, "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,PUT,OPTIONS" };
        if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        const endpoint = url.slice(productionBase.length);
        requests.push({ endpoint, method: request.method() });
        if (failSave && endpoint === "/users/me/rating-assessment") {
          failSave = false;
          return route.fulfill({ status: 503, headers, contentType: "application/json", body: JSON.stringify({ detail: "隔离测试：保存失败" }) });
        }
        const response = await route.fetch({ url: api + "/api/v1" + endpoint });
        return route.fulfill({ response, headers: { ...response.headers(), ...headers } });
      }
      if (url.startsWith(base + "/") || url.startsWith("data:") || url.startsWith("blob:")) return route.continue();
      return route.abort();
    });
    await context.addInitScript(({ token, productionBase }) => {
      // Do not overwrite stored drafts during reload; only seed local fixture credentials/preferences.
      localStorage.setItem("access_token", token);
      localStorage.setItem("session_context", "account-v2:web:" + productionBase);
      localStorage.setItem("discovery_city_v1", JSON.stringify({ type: "object", data: { city: "扬州市", region: ["江苏省", "扬州市", "广陵区"] } }));
    }, { token, productionBase });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(error.message));
    const visit = route => page.goto(base + "/#/pages/" + route, { waitUntil: "networkidle" });
    await visit("profile/edit");
    await page.getByText("测测我的等级", { exact: true }).click();
    await page.locator(".rating-card").first().waitFor();
    await page.waitForTimeout(350);
    assert.equal(await page.locator(".rating-card").count(), 4);
    assert.deepEqual(await page.locator(".rating-level").allTextContents(), ["1.5", "2.5", "3.5", "4.5"]);
    assert.match(await page.locator(".rating-footer .wd-button").getAttribute("class"), /is-disabled/);
    await page.screenshot({ path: path.join(output, "quick.png") });
    assert.equal(await page.locator(".rating-sheet").innerText().then(text => /UTR/.test(text)), false);
    await page.locator(".rating-card").filter({ hasText: "会打" }).locator(".wd-radio").click();
    failSave = true;
    await page.getByText("确认定级并保存", { exact: true }).click();
    await page.getByText("隔离测试：保存失败", { exact: true }).waitFor();
    assert.equal(await page.locator(".rating-card.chosen").count(), 1);
    await page.getByText("确认定级并保存", { exact: true }).click();
    await page.locator(".rating-sheet").waitFor({ state: "hidden" });
    assert.match(await page.locator(".picker-field").innerText(), /3\.5/);
    await page.reload({ waitUntil: "networkidle" });
    assert.match(await page.locator(".picker-field").innerText(), /3\.5/);
    await page.getByText("测测我的等级", { exact: true }).click();
    await page.getByText("做完整问卷（更细致）", { exact: true }).click();
    for (let step = 0; step < 6; step++) {
      await page.locator(".rating-progress").filter({ hasText: `${step + 1} / 6` }).waitFor();
      await page.locator(".rating-card .wd-radio").nth(3).click();
      if (!step) await page.screenshot({ path: path.join(output, "full.png") });
      await page.getByText(step === 5 ? "完成并保存" : "下一题", { exact: true }).click();
    }
    await page.locator(".rating-sheet").waitFor({ state: "hidden" });
    assert.match(await page.locator(".picker-field").innerText(), /3\.5/);
    await visit("profile/index");
    await page.getByText("NTRP 3.5", { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, "profile-tag.png") });
    // Actual form drafts survive page reconstruction and keep separate activity types.
    await visit("publish/post-create");
    await page.locator(".post-entry .wd-button:not(.is-disabled)").waitFor();
    await page.getByText("创建约球", { exact: true }).click();
    await page.locator(".post-form input").first().fill("退出后继续填写的约球");
    await page.getByText("保存草稿", { exact: true }).click();
    await page.getByText("草稿已保存，可退出后继续填写", { exact: true }).waitFor();
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.locator(".post-form input").first().inputValue(), "退出后继续填写的约球");
    await visit("publish/tournament-create");
    await page.locator("#required-title + .wd-input input").fill("退出后继续填写的比赛");
    await page.getByText("保存草稿", { exact: true }).click();
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.locator("#required-title + .wd-input input").inputValue(), "退出后继续填写的比赛");
    await visit("publish/post-create");
    assert.equal(await page.locator(".post-form input").first().inputValue(), "退出后继续填写的约球");
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ok: true, screenshots: output, checks: ["quick selection", "save failure retry", "NTRP persists after reload", "six-question flow", "profile tag", "post draft reload", "tournament draft reload", "separate activity drafts"], apiRequests: requests.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
