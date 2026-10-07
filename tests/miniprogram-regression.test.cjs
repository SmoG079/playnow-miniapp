const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../miniprogram');
const read = f => fs.readFileSync(path.join(root, f), 'utf8');
const walk = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
function harness(overrides = {}) {
  const calls = [], timers = new Map(); let timerId = 0;
  const app = { globalData: { token: 'token', userInfo: { id: 1, phone: '13800138000' }, role: 'user', managedClubIds: [] }, requireLogin: () => true, isClubAdmin: () => false, request: async () => ({ items: [] }), listAll: async () => [], uploadFile: async () => ({ url: 'https://example.test/file.png' }), ...overrides };
  const wx = new Proxy({}, { get: (_, api) => arg => { calls.push({ api, arg }); } });
  function load(file) {
    const full = path.join(root, file); let captured; const module = { exports: {} };
    vm.runInNewContext(fs.readFileSync(full, 'utf8'), {
      module, exports: module.exports, wx, getApp: () => app, getCurrentPages: () => [],
      console: { log() {}, error() {}, warn() {} },
      Page: o => { captured = o; }, App: o => { captured = o; }, Component: o => { captured = o; },
      require: request => load(path.relative(root, path.resolve(path.dirname(full), request + (path.extname(request) ? '' : '.js')))),
      setTimeout: fn => { timers.set(++timerId, fn); return timerId; }, clearTimeout: id => timers.delete(id),
      setInterval: fn => { timers.set(++timerId, fn); return timerId; }, clearInterval: id => timers.delete(id),
    }, { filename: full });
    if (!captured) return module.exports;
    const page = Object.assign(captured, captured.methods);
    page.data = JSON.parse(JSON.stringify(page.data || {}));
    page.setData = function(values, cb) {
      for (const [key, value] of Object.entries(values)) {
        const parts = key.split('.'); let obj = this.data;
        while (parts.length > 1) { const part = parts.shift(); obj = obj[part] ||= {}; }
        obj[parts[0]] = value;
      }
      if (cb) cb();
    };
    return page;
  }
  return { app, calls, timers, load };
}
const tap = (rowIdx, colIdx = 0) => ({ currentTarget: { dataset: { rowIdx, colIdx } } });
const cell = (id, start, end, price = 0, venue = 1) => ({ slot_id: id, venue_id: venue, start_time: start, end_time: end, price, date: '2099-01-01', status: 'available', _sel: false });
const validPost = { title: 'Match', preferredDate: '2099-01-01', preferredStart: '10:00', preferredEnd: '11:00', price: '0', playersNeeded: '2' };

test('30 registered complete page sets, no unregistered files or missing event handlers', () => {
  const app = JSON.parse(read('app.json')); assert.equal(app.pages.length, 30);
  assert.equal(walk(path.join(root, 'pages')).filter(f => f.endsWith('.js')).length, 30);
  for (const route of app.pages) {
    for (const ext of ['js', 'json', 'wxml', 'wxss']) assert(fs.existsSync(path.join(root, route + '.' + ext)));
    const p = harness().load(route + '.js'), xml = read(route + '.wxml');
    for (const b of xml.matchAll(/\b(?:bind|catch):?[\w-]+\s*=\s*"([^"]+)"/g)) assert.equal(typeof p[b[1]], 'function', route + ': ' + b[1]);
    for (const e of xml.matchAll(/\{\{([\s\S]*?)\}\}/g)) assert(!/\b\w+\s*\(/.test(e[1]), route + ': ' + e[1]);
  }
  assert(!fs.existsSync(path.join(root, 'pages/booking/club-detail.json')));
});
test('all native JS/JSON parse and fallback assets exist', () => {
  for (const f of walk(root)) {
    const s = fs.readFileSync(f, 'utf8');
    if (f.endsWith('.js')) new vm.Script(s, { filename: f });
    if (f.endsWith('.json')) JSON.parse(s);
    if (/\.(js|wxml|wxss)$/.test(f)) for (const m of s.matchAll(/\/images\/[\w.-]+/g)) assert(fs.existsSync(path.join(root, m[0])), m[0]);
  }
});
test('ordinary users have a publishing entry without managed clubs', async () => {
  let requests = 0; const h = harness({ request: async () => { requests++; } });
  const tab = h.load('custom-tab-bar/index.js'); tab.openActionSheet();
  assert(tab.data.actionSheetItems.some(x => x.page === '/pages/publish/post-create'));
  const p = h.load('pages/publish/post-create.js'); await p.loadClubs(); assert.equal(requests, 0);
});
test('free posts submit dates without club or booking', async () => {
  const requests = []; const h = harness({ request: async r => { requests.push(r); return {}; } });
  const p = h.load('pages/publish/post-create.js'); p.setData(validPost); await p.onSubmit();
  assert.equal(requests.length, 1); assert.equal(requests[0].data.club_id, null); assert.equal(requests[0].data.booking_id, null);
  assert.equal(requests[0].data.level_required, null); assert.equal(requests[0].data.preferred_date, validPost.preferredDate);
  for (const handler of ['onDateChange', 'onTimeStart', 'onTimeEnd']) assert(read('pages/publish/post-create.wxml').includes(handler));
});
test('invalid people, missing venue booking and failed uploads cannot create posts', async () => {
  let requests = 0; const h = harness({ request: async () => { requests++; }, uploadFile: async () => { throw Error('offline'); } });
  const p = h.load('pages/publish/post-create.js'); p.setData({ ...validPost, playersNeeded: '0' }); await p.onSubmit();
  p.setData({ playersNeeded: '1', matchMode: 'venue', clubIndex: 0 }); await p.onSubmit();
  p.setData({ matchMode: 'free', images: ['local.png'] }); await p.onSubmit();
  assert.equal(requests, 0); assert.equal(p.data.loading, false);
});
test('double submission sends one post request', async () => {
  let release, count = 0; const h = harness({ request: () => { count++; return new Promise(r => { release = r; }); } });
  const p = h.load('pages/publish/post-create.js'); p.setData(validPost);
  const first = p.onSubmit(); await Promise.resolve(); await p.onSubmit(); assert.equal(count, 1); release({}); await first;
});
test('cancelled phone authorization never sends a development code', () => {
  let count = 0; const h = harness({ request: () => { count++; } });
  h.load('pages/profile/edit.js').onGetPhoneNumber({ detail: { errMsg: 'cancel' } }); assert.equal(count, 0);
});
test('temporary avatar uploads before saving', async () => {
  const order = []; const h = harness({ uploadFile: async () => { order.push('upload'); return { url: 'https://example.test/avatar.png' }; }, request: async r => { order.push(r.data.avatar_url); }, fetchUserInfo: async () => {} });
  const p = h.load('pages/profile/edit.js'); p.setData({ nickname: 'Player', avatarUrl: 'wxfile://avatar.png' }); await p.onSubmit();
  assert.deepEqual(order, ['upload', 'https://example.test/avatar.png']);
});
test('logout clears permissions and transient booking state', () => {
  const app = harness().load('app.js'); Object.assign(app.globalData, { token: 'x', role: 'platform_admin', managedClubIds: [1], _bookingReturn: {} }); app.clearSession();
  assert.equal(app.globalData.role, 'user'); assert.equal(app.globalData.managedClubIds.length, 0); assert.equal(app.globalData._bookingReturn, null);
});
test('concurrent token refresh uses one exchange', async () => {
  const app = harness().load('app.js'); let refreshes = 0, release; const results = [];
  app.request = ({ url }) => url === '/auth/refresh' ? (refreshes++, new Promise(r => { release = r; })) : Promise.resolve('ok');
  const a = app.refreshTokenAndRetry({ url: '/a', resolve: r => results.push(r), reject: assert.fail });
  const b = app.refreshTokenAndRetry({ url: '/b', resolve: r => results.push(r), reject: assert.fail });
  assert.equal(refreshes, 1); release({ access_token: 'new', refresh_token: 'r' }); await a; await b; assert.equal(results.length, 2);
});
test('listAll includes pages after the first fifty records', async () => {
  const app = harness().load('app.js'); const requests = [];
  app.request = async ({ url }) => { requests.push(url); return { items: requests.length === 1 ? Array(50).fill({ id: 1 }) : [{ id: 2 }], total: 51 }; };
  assert.equal((await app.listAll('/clubs')).length, 51); assert(requests[1].includes('page=2'));
});
test('club reset is awaitable; clicking selected sort does not toggle', async () => {
  const p = harness().load('pages/booking/club-list.js'); await p.resetAndLoadClubs();
  p.onSortToggle({ currentTarget: { dataset: { value: 'default' } } }); assert.equal(p.data.sortBy, 'default');
});
test('stale club response cannot overwrite newest search', async () => {
  const requests = []; const p = harness({ request: () => new Promise(r => requests.push(r)) }).load('pages/booking/club-list.js');
  const a = p.loadClubs(), b = p.loadClubs(); requests[1]({ items: [{ id: 2 }] }); await b; requests[0]({ items: [{ id: 1 }] }); await a; assert.equal(p.data.clubs[0].id, 2);
});
test('one 60-minute zero-price slot is bookable', () => {
  const p = harness().load('pages/booking/venue-detail.js'); p.setData({ grid: [{ cells: [cell(1, '10:00', '11:00')] }] }); p.onSlotTap(tap(0));
  assert(p.data.selectedInfo); assert.equal(p.data.totalPrice, '0.00'); assert.equal(p.data.selectedSlots.length, 1);
});
test('consecutive selection uses actual times rather than adjacent grid rows', () => {
  const p = harness().load('pages/booking/venue-detail.js'); p.setData({ grid: [{ cells: [cell(1, '10:00', '11:00')] }, { cells: [{ status: 'none' }] }, { cells: [cell(2, '11:00', '11:30')] }] });
  p.onSlotTap(tap(0)); p.onSlotTap(tap(2)); assert.equal(p.data.selectedSlots.length, 2);
});
test('cross-court and discontinuous selection rejected; deselection trims suffix', () => {
  const p = harness().load('pages/booking/venue-detail.js'); p.setData({ grid: [{ cells: [cell(1, '10:00', '10:30', 10), cell(11, '10:00', '11:00', 10, 2)] }, { cells: [cell(2, '10:30', '11:00', 10)] }, { cells: [cell(3, '12:00', '13:00', 10)] }] });
  p.onSlotTap(tap(0)); assert.equal(p.data.selectedSlots.length, 2); p.onSlotTap(tap(0, 1)); p.onSlotTap(tap(2)); assert.equal(p.data.selectedSlots.length, 2);
  p.onSlotTap(tap(1)); assert.equal(p.data.selectedSlots.length, 1); assert.equal(p.data.selectedInfo, null);
});
test('confirmation login redirect preserves old slot ID and tournament return mode', () => {
  let target; const p = harness({ requireLogin: o => { target = o.redirect; return false; } }).load('pages/booking/confirm.js');
  p.onLoad({ slot_id: '7', return_mode: 'tournament', venue_name: 'Court & A' }); const q = new URL('https://test' + target).searchParams;
  assert.equal(q.get('slot_id'), '7'); assert.equal(q.get('return_mode'), 'tournament'); assert.equal(q.get('venue_name'), 'Court & A');
});
test('temporary payment preserved; tournament no longer a Tab', () => {
  const code = read('pages/booking/confirm.js'); assert(code.includes("title: '支付成功'")); assert(code.includes("const tabPages = ['post-create'];")); assert(!code.includes('wx.requestPayment('));
});
test('tournament booking return restores actual time', () => {
  const h = harness(); h.app.globalData._bookingReturn = { booking_id: 1, venue_id: 2, venue_name: 'Court', slot_date: '2099-01-01', slot_start: '10:00:00', slot_end: '12:00:00' };
  const p = h.load('pages/publish/tournament-create.js'); p.onShow(); assert.equal(p.data.form.start_time, '2099-01-01T10:00'); assert.equal(h.app.globalData._bookingReturn, null);
});
test('payment polling stops after twenty network errors', async () => {
  let count = 0; const h = harness({ request: async () => { count++; throw Error('offline'); } }); const p = h.load('pages/booking/success.js');
  p.setData({ booking: { status: 'pending' }, polling: true }); p._startPolling();
  for (let i = 0; i < 25 && h.timers.size; i++) { const [id, fn] = h.timers.entries().next().value; h.timers.delete(id); await fn(); }
  assert.equal(count, 20); assert.equal(p.data.polling, false); assert.equal(h.timers.size, 0);
});
test('manual address changes discard map coordinates', () => {
  const p = harness().load('pages/publish/club-create.js'); p.setData({ address: 'Old', latitude: 1, longitude: 2 }); p.onAddressInput({ detail: { value: 'New' } }); assert.equal(p.data.latitude, null);
});
test('numeric picker value chooses date-range price rule', () => {
  const p = harness().load('pages/publish/venue-manage.js'); p.onAddRule(); p.onRuleTypeChange({ currentTarget: { dataset: { idx: 0 } }, detail: { value: 0 } }); assert.equal(p.data.form.price_rules[0].type, 'date_range');
});
test('normal user does not request tournaments', async () => {
  const urls = []; const p = harness({ listAll: async u => { urls.push(u); return []; } }).load('pages/profile/my-posts.js'); await p.loadData(); assert.deepEqual(urls, ['/users/me/posts']);
});
test('multi-club manager queries only managed clubs', async () => {
  const urls = []; const h = harness({ isClubAdmin: () => true, listAll: async u => { urls.push(u); return []; } }); h.app.globalData.managedClubIds = [2, 4];
  await h.load('pages/profile/my-posts.js').loadData(); assert.deepEqual(urls, ['/users/me/posts', '/tournaments?club_id=2', '/tournaments?club_id=4']);
});
test('backend free-post queries include unattached posts; migration preserves data', () => {
  const posts = read('../backend/app/api/v1/posts.py'), users = read('../backend/app/api/v1/users.py');
  assert.equal((posts.match(/\.outerjoin\(Club, MatchPost.club_id == Club.id\)/g) || []).length, 2); assert(users.includes('.outerjoin(Club, MatchPost.club_id == Club.id)'));
  const migration = read('../backend/alembic/versions/20260904_free_posts.py'); assert(migration.includes('nullable=True')); assert(migration.includes('if count:')); assert(!/DELETE FROM|DROP TABLE/i.test(migration));
});
