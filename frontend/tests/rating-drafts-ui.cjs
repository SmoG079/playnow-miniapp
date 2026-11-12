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
    const productionBase = "https://www.tennisplaynow.site/api/v1";
    const errors = [], requests = [];
    let failSave = false;
    await context.route("**/*", async route => {
      const request = route.request(), url = request.url();
      if (url.startsWith(productionBase + "/")) {
        const headers = { "access-control-allow-origin": base, "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,POST,PUT,OPTIONS" };
        if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
        const endpoint = url.slice(productionBase.length);
        requests.push({ endpoint, method: request.method() });
        if (failSave && endpoint === "/users/me" && request.method() === "PUT") {
          failSave = false;
          return route.fulfill({ status: 503, headers, contentType: "application/json", body: JSON.stringify({ detail: "隔离测试：保存失败" }) });
        }
        const response = await route.fetch({ url: api + "/api/v1" + endpoint });
        return route.fulfill({ response, headers: { ...response.headers(), ...headers } });
      }
      if (url.startsWith(base + "/") || url.startsWith("data:") || url.startsWith("blob:")) return route.continue();
      return route.abort();
    });
    await context.addInitScript(({ token }) => {
      // Do not overwrite stored drafts during reload; only seed local fixture credentials/preferences.
      localStorage.setItem("access_token", token);
      localStorage.setItem("session_context", "account-v2:web:https://www.tennisplaynow.site:8443/api/v1");
      localStorage.setItem("discovery_city_v1", JSON.stringify({ type: "object", data: { city: "扬州市", region: ["江苏省", "扬州市", "广陵区"] } }));
    }, { token });
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(error.message));
    const visit = route => page.goto(base + "/#/pages/" + route, { waitUntil: "networkidle" });
    await visit("profile/edit");
    await page.getByText("测测我的等级", { exact: true }).click();
    await page.locator(".rating-card").first().waitFor();
    await page.waitForTimeout(350);
    assert.equal(await page.locator(".rating-card").count(), 4);
    assert.deepEqual(await page.locator(".rating-level").allTextContents(), ["2.0", "2.5", "3.0", "4.0"]);
    assert.match(await page.locator(".rating-footer .wd-button").getAttribute("class"), /is-disabled/);
    await page.screenshot({ path: path.join(output, "quick.png") });
    assert.equal(await page.locator(".rating-sheet").innerText().then(text => /UTR/.test(text)), false);
    await page.locator(".rating-card").filter({ hasText: "稳定对拉" }).click();
    failSave = true;
    await page.getByText("确认定级并保存", { exact: true }).click();
    await page.getByText("隔离测试：保存失败", { exact: true }).waitFor();
    assert.equal(await page.locator(".rating-card.is-checked").count(), 1);
    await page.getByText("确认定级并保存", { exact: true }).click();
    await page.locator(".rating-sheet").waitFor({ state: "hidden" });
    assert.match(await page.locator(".picker-field").innerText(), /3\.0/);
    await page.reload({ waitUntil: "networkidle" });
    assert.match(await page.locator(".picker-field").innerText(), /3\.0/);
    await page.getByText("测测我的等级", { exact: true }).click();
    await page.getByText("做完整问卷（更细致）", { exact: true }).click();
    const calibrationOptions = [3, 4, 1, 3, 3, 3, 3];
    for (const [step, option] of calibrationOptions.entries()) {
      await page.locator(".rating-progress").filter({ hasText: `${step + 1} / 7` }).waitFor();
      const cards = page.locator(".rating-card");
      const selected = page.locator(".rating-card.is-checked");
      assert.equal(await selected.count(), 0);
      if (step === 5) {
        await cards.nth(1).click();
        assert.deepEqual(await selected.allTextContents(), ["能截击正面的慢球"]);
      }
      await cards.nth(option).click();
      assert.deepEqual(await selected.allTextContents(), [await cards.nth(option).textContent()]);
      if (!step) await page.screenshot({ path: path.join(output, "full.png") });
      await page.getByText(step === 6 ? "查看结果" : "下一题", { exact: true }).click();
    }
    await page.locator(".rating-result-score").getByText("NTRP 3.0", { exact: true }).waitFor();
    await page.locator(".rating-weakness").getByText(/反手/).waitFor();
    assert.equal(requests.filter(({ endpoint, method }) => endpoint === "/users/me" && method === "PUT").length, 2);
    await page.getByText("返回修改", { exact: true }).click();
    await page.locator(".rating-progress").filter({ hasText: "7 / 7" }).waitFor();
    assert.match(await page.locator(".rating-card.is-checked").innerText(), /调整战术/);
    await page.getByText("查看结果", { exact: true }).click();
    failSave = true;
    await page.getByText("保存等级", { exact: true }).click();
    await page.getByText("隔离测试：保存失败", { exact: true }).waitFor();
    await page.locator(".rating-result-score").getByText("NTRP 3.0", { exact: true }).waitFor();
    await page.getByText("保存等级", { exact: true }).click();
    await page.locator(".rating-sheet").waitFor({ state: "hidden" });
    assert.match(await page.locator(".picker-field").innerText(), /3\.0/);
    await visit("profile/index");
    await page.getByRole("button", { name: "编辑个人资料" }).getByText("NTRP 3.0", { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, "profile-tag.png") });
    // Actual form drafts survive page reconstruction and keep separate activity types.
    await visit("publish/index");
    await page.getByText("发布约球", { exact: true }).click();
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
    assert(!requests.some(({ endpoint }) => /rating-(questionnaire|assessment)$/.test(endpoint)));
    console.log(JSON.stringify({ ok: true, screenshots: output, checks: ["quick selection", "save failure retry", "NTRP persists after reload", "seven-question calibration and preview", "profile tag", "post draft reload", "tournament draft reload", "separate activity drafts"], apiRequests: requests.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
