# 模块 B（预约 & 支付）多轮评审汇总报告 V2

## 评审日期 / 范围 / 方法

- **评审日期**: 2026-06-13
- **评审范围**: B-01 至 B-08 需求，覆盖后端 API（`bookings.py`、`venues.py`、`tasks.py`、`settlement.py`、`models.py`）、前端页面（`app.js`、`confirm.js`、`success.js`、`wxpay.js`、`my-bookings.js`、`venue-detail.js`、`club-list.js`）、WeChat 支付 V3 回调安全、Redis 分布式锁、Celery 异步任务
- **评审方法**:
  1. 三轮独立评审：后端代码评审 Agent、前端代码评审 Agent、支付/安全专项评审 Agent
  2. Web 搜索 WeChat Pay V3 JSAPI、退款、Redis 锁、取消策略等权威资料
  3. 交叉核对：将三轮发现的问题相互印证，去除误报，合并重复项
  4. 按 P0/P1/P2 分级，形成可执行的问题清单
  5. 对高置信度 P0 问题提出修复建议

---

## P0 阻断级问题

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| P0-1 | **TOCTOU 竞态条件**：`create_booking` 先检查 `slot.status == available`（line 67），再获取 Redis 锁（line 81），中间无 DB 行锁。并发请求可能同时通过检查，第二个获取 Redis 锁失败但竞态窗口已打开 | `backend/app/api/v1/bookings.py:67-83` | 超卖：同一 slot 可能被多个用户同时创建订单 | 使用 `SELECT FOR UPDATE` 锁定 slot 行，或将状态检查与 Redis 锁获取合并为原子操作 |
| P0-2 | **Redis 锁在 DB 事务外**：`acquire_lock`（line 81）在 `try` 块外，且 `try` 块内才启动 DB 事务。如果 Redis 锁获取后、DB 提交前进程崩溃，Redis 锁 TTL 到期前 slot 被永久锁定 | `backend/app/api/v1/bookings.py:79-106` | 锁与 DB 状态不一致，slot 可能永久不可用 | 将 Redis 锁获取移入 `try` 块，或确保 Redis 锁 TTL 与 DB 事务绑定；异常时释放锁 |
| P0-3 | **Decimal 转 cents 截断**：`int(order.amount * 100)` 和 `int(refund_amount * 100)` 直接截断 Decimal，可能导致 1 分钱误差 | `backend/app/api/v1/bookings.py:238, 694, 813` | 微信支付金额与实际订单金额不一致 | 使用 `Decimal.quantize` 或 `round()` 正确转换：`int((amount * 100).quantize(Decimal('1')))` |
| P0-4 | **回调签名验证顺序错误**：`wx_pay_notify` 先 `json.loads(body)` 解析外层通知，再调用 `decrypt_callback(request.headers, body)`。WeChat Pay V3 要求先验证签名再解密，且签名验证需要原始 body | `backend/app/api/v1/bookings.py:256-296` | 回调可能被伪造，攻击者注入虚假支付成功通知 | 先调用 `decrypt_callback(headers, body)` 验证签名并解密，再解析解密后的数据 |
| P0-5 | **回调处理重工作阻塞响应**：`_handle_payment_success` 和 `_handle_refund_callback` 在返回 `{"code": "SUCCESS"}` 前执行大量 DB 操作（slot 状态更新、settlement 创建、通知写入）。WeChat 要求 5 秒内返回 | `backend/app/api/v1/bookings.py:319-421, 424-577` | 超时导致 WeChat 重试，可能产生重复通知处理 | 收到回调后立即返回 SUCCESS，将后续处理放入 Celery 异步任务 |
| P0-6 | **无时间戳/重放保护**：回调处理未检查 `Wechatpay-Timestamp` 与当前时间的差值，未检查 `Wechatpay-Nonce` 是否已使用过 | `backend/app/api/v1/bookings.py:256-296` | 重放攻击：攻击者重复发送旧回调导致重复发货/退款 | 验证时间戳（如 |now - timestamp| > 300s 则拒绝），并在 Redis 中记录已处理 nonce |
| P0-7 | **回调未校验金额**：`TRANSACTION.SUCCESS` 回调未比对 `data.amount.total` 与订单 `order.amount` 是否一致 | `backend/app/api/v1/bookings.py:319-421` | 金额篡改攻击：用户支付更少金额但系统标记为全额支付 | 校验回调金额与订单金额一致（允许 1 分钱浮差） |
| P0-8 | **`release_expired_locks` 无所有权校验**：释放 Redis 锁时调用 `release_lock(lock_key)` 未传入 `value` 参数，可能误释放其他用户持有的锁 | `backend/app/tasks/tasks.py:40` | 竞态条件下 Celery 可能释放另一个用户刚获取的新锁 | 传入 `slot.locked_by` 作为 `value` 参数，调用 `release_lock(lock_key, str(slot.locked_by))` |
| P0-9 | **`app.js` request() 拒绝 201 Created**：`success` 回调仅处理 `statusCode === 200`，201 被落入 `else` 分支报错 | `miniprogram/app.js:60-66` | 所有返回 201 的 POST/PUT API 前端都会报错 | 将 `res.statusCode >= 200 && res.statusCode < 300` 视为成功 |
| P0-10 | **`refreshTokenAndRetry` 无限递归**：`refreshTokenAndRetry` 内部调用 `this.request()`，如果刷新接口本身返回 401（如 refresh_token 过期），会再次触发 `refreshTokenAndRetry`，形成无限递归 | `miniprogram/app.js:77-98` | 栈溢出，应用崩溃 | 在 `request` 中标记 "正在刷新" 状态，或让刷新请求使用特殊路径不走统一拦截 |
| P0-11 | **`confirm.js` 无登录守卫**：`onLoad` 和 `onPay` 未检查用户是否登录，未登录用户点击支付会触发失败 | `miniprogram/pages/booking/confirm.js:19-103` | 未登录用户进入确认页，支付失败体验差 | 在 `onLoad` 或 `onShow` 中调用 `app.requireLogin()` |
| P0-12 | **`wxpay.js` 无参数校验**：`payOrder` 未校验 `payParams` 字段完整性（`timeStamp`、`nonceStr`、`package`、`paySign` 是否缺失）直接传入 `wx.requestPayment` | `miniprogram/utils/wxpay.js:8-37` | 后端返回异常时前端直接调用支付，可能导致支付参数错误 | 在调用 `wx.requestPayment` 前校验所有必需字段存在且非空 |

---

## P1 高优先级问题

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| P1-1 | **时区 bug（取消规则）**：`cancel_booking` 使用 `datetime.now(tz)` 与 `slot_datetime` 计算 `hours_before`，但 `now` 变量被转换为 UTC naive 后未使用，实际比较用的是 `now_aware`（Asia/Shanghai）与 `slot_datetime`（Asia/Shanghai），逻辑正确但代码混乱；更关键的是 `slot.locked_at` 在 `create_booking` 中存储的是 `datetime.utcnow()`（UTC naive），而 `pay_booking` 中比较用的是 `datetime.utcnow()`，两者一致，但整个系统混用 UTC naive 和 timezone-aware 时间 | `backend/app/api/v1/bookings.py:653-657, 89, 216` | 时区不一致导致时间计算错误，特别是夏令时切换期 | 统一使用 `datetime.now(timezone.utc)` 或统一使用 Asia/Shanghai aware 时间 |
| P1-2 | **`create_booking` 未校验 slot 是否在未来**：允许创建过去时间的预约订单 | `backend/app/api/v1/bookings.py:53-66` | 用户可以预订已过去的场次 | 检查 `slot.date` + `slot.start_time` 必须大于当前时间 |
| P1-3 | **Celery `asyncio.run` 创建新事件循环**：每个任务调用 `asyncio.run(_run())` 创建并销毁新事件循环，开销大且可能引发资源泄漏 | `backend/app/tasks/tasks.py:56, 110, 157, 287, 342` | 性能问题，长时间运行后可能耗尽文件描述符 | 使用 `asgiref.sync.async_to_sync` 或让 Celery worker 使用 `asyncio` 兼容模式 |
| P1-4 | **退款回调幂等性缺口**：`REFUND.SUCCESS` 回调未检查订单是否已经是 `refunded` 状态就更新，虽然对 `order.status` 有检查，但 `refund_record` 的更新无状态机保护 | `backend/app/api/v1/bookings.py:461-508` | 重复回调可能导致重复释放 slot、重复通知 | 在更新 `refund_record` 前检查其当前状态，已 `success` 则跳过 |
| P1-5 | **分账 `unfreeze_unsplit=True` 无条件**：`execute_settlement` 中 `profitsharing_order` 总是设置 `unfreeze_unsplit=True`，即使分账失败也会解冻未分资金 | `backend/app/services/settlement.py:134` | 分账失败时资金被错误解冻，平台/俱乐部损失 | 仅在确认分账成功后才解冻，或根据业务规则配置 |
| P1-6 | **分账 receiver sum 调整未更新 DB**：`settlement.py:112-123` 调整 `club_amount_cents` / `platform_amount_cents` 后仅更新了 `receivers` dict，未同步更新 `settlement.club_amount` / `settlement.platform_amount` | `backend/app/services/settlement.py:112-123` | DB 记录的分账金额与实际发送给微信的金额不一致 | 调整 cents 后同步更新 `settlement.club_amount` 和 `settlement.platform_amount` |
| P1-7 | **无速率限制**：`pay_booking`、`cancel_booking`、`refund_booking` 等敏感操作无速率限制 | 全局 | 暴力重试、刷单、退款攻击 | 在 API 层添加 Redis 速率限制（如每用户每分钟最多 10 次支付请求） |
| P1-8 | **`success.js` 成功图标对所有非 pending 状态显示**：`success.wxml` 的 `success-header` 和 `success-icon` 对 `paid`、`cancelled`、`refunded` 都显示相同的成功样式 | `miniprogram/pages/booking/success.wxml:8-11` | 支付失败/取消后用户仍看到成功图标，体验混乱 | 根据 `booking.status` 显示不同图标和文案（成功/失败/取消） |
| P1-9 | **`confirm.js` 无支付倒计时**：用户锁定 slot 后无倒计时提示，不知道还剩多少时间 | `miniprogram/pages/booking/confirm.js` | 用户可能超时未支付，锁自动释放但用户不知情 | 添加倒计时显示（从 `locked_at` + TTL 计算剩余时间） |
| P1-10 | **`my-bookings` 硬编码 24h 退款阈值**：前端使用固定 24 小时计算退款比例，与后端 `FREE_CANCEL_HOURS` 配置可能不一致 | `miniprogram/pages/profile/my-bookings.js:99-108` | 前后端退款规则不一致，用户看到的退款金额与实际不符 | 从后端配置读取退款阈值，或后端在订单详情中返回 `refund_preview` |
| P1-11 | **`my-bookings` 通过 `data-booking` 传递完整对象**：WXML 中 `data-booking="{{item}}"` 传递整个 booking 对象，对象序列化/反序列化可能丢失数据 | `miniprogram/pages/profile/my-bookings.wxml:50-58` | 数据不一致，大对象传递性能差 | 仅传递 `booking.id`，事件处理中通过 ID 从列表查找 |
| P1-12 | **`RefundRecord` 缺少 `updated_at` 但任务查询它**：`poll_processing_refunds` 查询 `RefundRecord.updated_at <= one_min_ago`，但模型定义中无 `updated_at` 字段 | `backend/app/models/models.py:388-410`, `backend/app/tasks/tasks.py:307` | SQL 查询 `updated_at` 列不存在，任务执行报错 | 在 `RefundRecord` 模型中添加 `updated_at` 列，或修改查询条件使用 `created_at` |

---

## P2 中/低优先级问题

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| P2-1 | **`BookingOrder.order_no` 缺少索引**：`order_no` 是 `unique=True` 但无独立索引，查询时全表扫描 | `backend/app/models/models.py:168` | 回调查询、订单查询性能差 | 为 `order_no` 添加 `index=True` |
| P2-2 | **`refund_status` 使用普通字符串而非 Enum**：`BookingOrder.refund_status` 和 `RefundRecord.status` 都是 `String` 而非 `Enum` | `backend/app/models/models.py:184, 397` | 缺少数据库级约束，可能出现非法值 | 改为 `Enum` 类型，与 `OrderStatus`、`SettlementStatus` 保持一致 |
| P2-3 | **`_refund_slot_release` 死代码**：函数定义在 `bookings.py:737-743` 但从未被调用 | `backend/app/api/v1/bookings.py:737-743` | 维护负担，误导开发者 | 删除或替换内联重复代码 |
| P2-4 | **`update_slot_status` 死/不可达代码**：`return {"msg": "ok"...}` 在 line 240，之后的 `price` 和 `SlotBrief` 返回代码永远不会执行 | `backend/app/api/v1/venues.py:240-252` | 逻辑错误，API 实际返回 dict 而非 `SlotBrief` schema | 删除死代码或修复返回类型 |
| P2-5 | **`venue-detail` 网格未区分 `locked`/`booked` 视觉状态**：`locked` 和 `booked` 都显示 "不可订"，用户无法区分 | `miniprogram/pages/booking/venue-detail.wxml:92-96` | 体验差，用户不知道槽位是否可能释放 | 为 `locked` 状态添加 "锁定中" 视觉样式 |
| P2-6 | **`club-list` 缺少 `onReachBottom` 分页**：`loadClubs` 只加载第 1 页，无翻页逻辑 | `miniprogram/pages/booking/club-list.js:45-65` | 俱乐部列表只能显示前 20 条 | 添加 `onReachBottom` 和 `page` 计数器 |
| P2-7 | **`club-detail` 是空占位符**：`club-detail.js` 和 `wxml` 无任何内容 | `miniprogram/pages/booking/club-detail.js:1`, `club-detail.wxml:1` | 页面不可用 | 实现俱乐部详情页或从导航中移除 |
| P2-8 | **`venue-detail/club-list` 导航命名混乱**：`club-list` 中点击俱乐部跳转到 `venue-detail`（实际为俱乐部详情+场地选择），命名不一致 | `miniprogram/pages/booking/club-list.js:107` | 代码可读性差，维护困难 | 统一命名：俱乐部列表 → 场地选择页 |
| P2-9 | **文档与实现不同步**：`workflow-backend-api.md`、`功能审计报告` 等文档中部分 API 描述与最新实现不一致 | `docs/` | 维护困难，新开发者容易误解 | 更新文档中已过时的限制项和 API 描述 |

---

## 跨领域主题

### 1. 时区一致性
- **问题**：系统混用 `datetime.utcnow()`（UTC naive）、`datetime.now(tz)`（aware）、`ZoneInfo("Asia/Shanghai")`（aware）三种时间表示
- **影响**：取消规则计算、锁超时判断、分账调度时间可能因时区不一致而出错
- **建议**：统一使用 `datetime.now(timezone.utc)` 存储，仅在展示层转换为本地时区

### 2. 金额精度（Decimal → cents）
- **问题**：多处使用 `int(amount * 100)` 直接截断 Decimal，未使用 `quantize`
- **影响**：1 分钱误差累积，微信支付金额与订单金额不一致
- **建议**：统一使用 `settlement.py` 中已定义的 `_to_cents()` 函数，或将其提取到公共模块

### 3. 回调安全（WeChat Pay V3）
- **问题**：签名验证顺序错误、无重放保护、无金额校验、重工作阻塞响应
- **影响**：伪造回调、重放攻击、金额篡改、WeChat 重试风暴
- **建议**：
  1. 严格遵循 "先验签 → 再解密 → 再处理" 流程
  2. 添加时间戳和 nonce 重放检查
  3. 校验回调金额与订单金额
  4. 立即返回 SUCCESS，异步处理业务逻辑

### 4. Redis 锁与 DB 一致性
- **问题**：锁获取在事务外、释放无所有权校验、静态 value `'locked'` 无法区分所有者
- **影响**：竞态条件、误释放、永久锁定
- **建议**：
  1. 锁 value 使用 `user_id` 或 `order_id`
  2. 释放时校验所有权（Lua 脚本）
  3. 将锁获取纳入 DB 事务边界

### 5. Celery 异步模式
- **问题**：`asyncio.run()` 在每个任务中创建新事件循环
- **影响**：性能开销、资源泄漏
- **建议**：使用 `asgiref.sync.async_to_sync` 或配置 Celery 使用 `asyncio` 兼容模式

### 6. 状态机完整性
- **问题**：`refund_status` 使用字符串、`RefundRecord` 缺少 `updated_at`、退款回调幂等性不足
- **影响**：状态不一致、重复处理
- **建议**：统一使用 Enum、补充缺失字段、加强幂等检查

---

## 推荐修复顺序

### 第一批次（立即修复 - P0）
1. **P0-4 回调签名验证顺序** + **P0-5 回调异步化** + **P0-6 重放保护** + **P0-7 金额校验** — 安全相关，必须优先
2. **P0-3 Decimal 转 cents** — 涉及资金安全
3. **P0-1 TOCTOU 竞态** + **P0-2 锁在事务外** + **P0-8 Celery 释放无所有权校验** — 核心 booking 逻辑
4. **P0-9 app.js 201 处理** + **P0-10 无限递归** + **P0-11 confirm 登录守卫** + **P0-12 wxpay 参数校验** — 前端阻断

### 第二批次（本周内 - P1）
5. **P1-1 时区统一** + **P1-2 过去时间校验**
6. **P1-3 Celery asyncio 优化**
7. **P1-4 退款回调幂等性** + **P1-12 RefundRecord updated_at**
8. **P1-5 unfreeze_unsplit 条件** + **P1-6 receiver sum 同步 DB**
9. **P1-7 速率限制**
10. **P1-8 success.js 状态图标** + **P1-9 confirm 倒计时** + **P1-10/P1-11 前端退款逻辑**

### 第三批次（下周 - P2）
11. **P2-1 order_no 索引** + **P2-2 refund_status Enum** + **P2-3/P2-4 死代码清理**
12. **P2-5 venue-detail 视觉区分** + **P2-6 club-list 分页** + **P2-7 club-detail 实现**
13. **P2-8 命名统一** + **P2-9 文档更新**

---

## 歧义 / 需确认

| # | 问题 | 说明 |
|---|------|------|
| Q1 | 取消规则到底是 2h 还是 24h？ | 需求 B-06 描述为 "开场前 2h"，但代码实现使用 `FREE_CANCEL_HOURS=24`。需业务方确认 |
| Q2 | `club-detail` 页面是否还需要？ | 当前 `club-detail` 是空占位符，但 `club-list` 直接跳转到 `venue-detail`。需确认是否保留独立俱乐部详情页 |
| Q3 | `unfreeze_unsplit` 的业务规则 | 当前无条件设置为 `True`，分账失败时也会解冻。需确认是否应在分账成功后才解冻 |
| Q4 | 退款回调的 `out_refund_no` 幂等键 | 当前退款重试使用新的 `out_refund_no`，但 WeChat 文档建议重试时复用同一个 `out_refund_no`。需确认实现是否符合预期 |
| Q5 | `release_expired_locks` 的 Redis 锁释放策略 | 当前 Celery 任务释放锁时不传 `value`，但 `acquire_lock` 已使用 `str(current_user.id)` 作为 value。需确认是否应统一所有权校验 |
| Q6 | 结算分账的 `sub_mchid` 参数 | `profitsharing_order` 传入 `sub_mchid=club.sub_merchant_id`，但 `receivers` 中也包含 `club.sub_merchant_id`。需确认是否重复或配置正确 |

---

## 已修复问题（评审前）

以下问题已在之前修复，本次评审确认代码已更新：

| 原编号 | 问题 | 修复文件 | 状态 |
|--------|------|----------|------|
| P0-1 (旧) | 确认订单页空占位符 | `confirm.wxml`/`confirm.wxss`/`confirm.js` | 已修复 |
| P0-2 (旧) | 支付成功页空占位符 | `success.js`/`success.wxml`/`success.wxss` | 已修复 |
| P0-3 (旧) | 取消规则时区计算错误 | `bookings.py` | 已修复 |
| P0-4 (旧) | 支付回调未验证 slot 锁定归属 | `bookings.py` | 已修复 |
| P0-5 (旧) | Celery `asyncio.get_event_loop()` 问题 | `tasks.py` | 已修复（改为 `asyncio.run()`） |
| P0-6 (旧) | 结算执行完全缺失 | `settlement.py` + `tasks.py` | 已修复 |
| P1-1/P1-2 (旧) | 前端缺少支付/退款入口 | `my-bookings.js`/`wxml` | 已修复 |
| P1-4 (旧) | 重复调用 `/{id}/pay` 无幂等控制 | `bookings.py` + `models.py` | 已修复 |
| P1-5 (旧) | 创建微信支付订单前未检查锁有效性 | `bookings.py` | 已修复 |
| P1-6 (旧) | `REFUND.CLOSED` 槽位回收状态不一致 | `bookings.py` | 已修复 |
| P1-7 (旧) | 未处理 `REFUND.ABNORMAL` | `bookings.py` | 已修复 |
| P1-8 (旧) | 退款重试机制缺失 | `tasks.py` + `models.py` | 已修复 |

---

*报告生成时间: 2026-06-13*
*评审 Agent: 后端代码评审 Agent、前端代码评审 Agent、支付/安全专项评审 Agent*
