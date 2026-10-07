# 模块 B（预约 & 支付）多 Agent 评审报告

## 评审日期
2026-06-13

## 评审范围
B-01 至 B-08 需求，覆盖后端 API、数据模型、前端页面、WeChat 支付最佳实践。

## 参与 Agent
- 后端代码评审 Agent
- 前端代码评审 Agent
- 规范/文档评审 Agent
- 外部参考研究 Agent（WeChat Pay、Redis、退款策略）

## 评审方法
1. 各 Agent 独立阅读代码、文档、规范
2. Web 搜索 WeChat Pay V3 JSAPI、退款、Redis 锁、取消策略等权威资料
3. 交叉核对：将 Agent 发现的问题相互印证，去除误报
4. 按 P0/P1/P2 分级，形成可执行的问题清单
5. 对高置信度 P0 问题提出修复建议

---

## 一、需求实现总览

| 编号 | 需求 | 后端状态 | 前端状态 | 整体 |
|------|------|----------|----------|------|
| B-01 | 选俱乐部 → 选场地 → 选日期 → 选时间段 → 确认 → 支付 | 已实现 | 部分实现（确认页为空） | ⚠️ 前端阻断 |
| B-02 | 已预约/锁定时间段自动灰显不可选 | 已实现 | 已实现但视觉区分不足 | ⚠️ 体验待优化 |
| B-03 | 下单后锁场 10 分钟，超时未支付自动释放 | 已实现 | 无倒计时提示 | ⚠️ 体验待优化 |
| B-04 | 微信 JSAPI 支付，支付成功生成订单，失败回滚锁 | 已实现 | 支付按钮缺失、成功页为空 | ⚠️ 前端阻断 |
| B-05 | "我的预约"列表：筛选、详情、取消 | 已实现 | 列表有，缺详情页、缺付费取消 | ⚠️ 功能不全 |
| B-06 | 取消规则：开场前 2h 免费取消，2h 内扣 50%，开场后不可取消 | 已实现但时区计算有 bug | 未暴露付费取消入口 | ⚠️ 后端 bug |
| B-07 | 退款：调用微信退款 API，原路返回 | 已实现 | 缺少退款状态 UI | ⚠️ 体验待优化 |
| B-08 | 包场/拼场模式（P2 扩展） | 未实现 | 未实现 | ❌ 待规划 |

> 注：当前需求 B-06 描述为"开场前 2h"，但代码实现使用 `FREE_CANCEL_HOURS=24`。该配置与需求不一致，需确认业务规则。

---

## 二、已交叉验证的高置信度问题

### P0 — 阻断级

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| P0-1 | 确认订单页 `confirm.wxml` 是占位符，无任何 UI 和支付按钮 | `miniprogram/pages/booking/confirm.wxml:1` | 用户无法查看订单摘要，也无法触发支付 | 重写 `confirm.wxml`/`.wxss`，展示订单信息并提供「确认支付」按钮 |
| P0-2 | 支付成功页 `success.wxml` 是占位符，无任何内容 | `miniprogram/pages/booking/success.wxml:1` | 支付后用户看到空白页 | 重写 `success.wxml`/`.js`，展示订单详情、跳转入口 |
| P0-3 | 取消规则使用时区错误的 `datetime.utcnow()` 与本地 naive 时间比较 | `backend/app/api/v1/bookings.py:551-553` | 开场前 8 小时内的退款/取消判断会出错 | 统一使用 `Asia/Shanghai` 时区或 timezone-aware 时间 |
| P0-4 | 支付回调里未验证 slot 仍由当前订单锁定就直接改为 `booked` | `backend/app/api/v1/bookings.py:317-324` | 锁过期后可能被重复预订 | 回调中检查 `slot.status == locked && slot.locked_by == order.user_id` |
| P0-5 | Celery 任务使用 `asyncio.get_event_loop()`，在 worker 中可能拿到已关闭的 loop | `backend/app/tasks/tasks.py:47-48` | 超时锁无法释放，场地永远被占用 | 改用 `asyncio.run()` 或 `asgiref.sync.async_to_sync` |
| P0-6 | 结算（分账）执行完全缺失：只有 `SettlementRecord` 创建，没有调用微信分账 API 的任务 | `backend/app/api/v1/bookings.py:326-341` | 平台无法向俱乐部结算 | 新增结算调度 Celery 任务和回调处理 |

### P1 — 高优先级

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| P1-1 | 前端「我的预约」缺少付费订单的取消/退款入口 | `miniprogram/pages/profile/my-bookings.js:61` | 用户无法主动退已付款订单 | 对 `paid` 状态也显示取消按钮，展示退款金额 |
| P1-2 | 前端「我的预约」缺少「立即支付」按钮 | `miniprogram/pages/profile/my-bookings.wxml:47-52` | 支付失败后只能重新下单 | 对 `pending` 状态增加支付按钮，复用 `wxpay.payBooking` |
| P1-3 | 前端「我的预约」无订单详情页 | `my-bookings.wxml` | 用户看不到完整订单和退款记录 | 新增 `/pages/booking/booking-detail` 或跳转 |
| P1-4 | 重复调用 `/{id}/pay` 无幂等控制 | `backend/app/api/v1/bookings.py:165-204` | 可能生成多个 prepay_id | 在 `BookingOrder` 记录 `prepay_id`，重复调用时复用或校验 |
| P1-5 | 创建微信支付订单前未检查锁是否仍有效 | `backend/app/api/v1/bookings.py:165-204` | 可能为已释放的slot生成支付 | 校验 `slot.locked_at` + `BOOKING_LOCK_TTL_SECONDS` |
| P1-6 | `REFUND.CLOSED` 槽位回收逻辑存在竞态且把 `booked` 槽位写入 `locked_by` | `backend/app/api/v1/bookings.py:454-473` | 槽位状态不一致 | 回收时 `locked_by = NULL, locked_at = NULL` |
| P1-7 | 没有处理 `REFUND.ABNORMAL` | `backend/app/api/v1/bookings.py:251` | 需人工审核的退款被静默忽略 | 增加 `ABNORMAL` 分支，标记订单/退款记录 |
| P1-8 | 退款重试机制缺失 | 全局 | 退款 API 临时失败后无自动重试 | 增加 Celery 重试任务 |

### P2 — 中优先级

| # | 问题 | 位置 | 影响 | 修复建议 |
|---|------|------|------|----------|
| P2-1 | 前端场地网格未区分 `locked` 与 `booked` 视觉状态 | `miniprogram/pages/booking/venue-detail.wxml:92-96` | 用户不知道槽位是否可能释放 | 增加「锁定中」视觉状态 |
| P2-2 | 前端确认页缺少倒计时、无取消按钮、无登录前置检查 | `confirm.js` / `venue-detail.js` | 体验差 | 增加倒计时、登录检查、离开页面时自动取消 |
| P2-3 | `refund_status` 使用普通字符串而非 Enum | `backend/app/models/models.py:181` | 缺少数据库级校验 | 改为 Enum |
| P2-4 | `_refund_slot_release` 辅助函数定义未使用 | `backend/app/api/v1/bookings.py:618-624` | 死代码 | 删除或复用 |
| P2-5 | 文档与实现不同步 | `docs/workflow-backend-api.md` 等 | 维护困难 | 更新已知限制、补充已实现功能 |

---

## 三、外部参考关键结论

### WeChat Pay V3 JSAPI
- 后端调用 `POST /v3/pay/transactions/jsapi`，前端使用 `wx.requestPayment({ timeStamp, nonceStr, package: 'prepay_id=xxx', signType: 'RSA', paySign })`。
- `timeStamp` 必须是字符串。
- 回调必须在 5 秒内返回 200/204。
- 回调签名必须使用**微信平台证书**，不是商户证书。
- 必须校验回调时间戳防重放。

### Redis 锁
- 推荐 `SET key value NX EX seconds` 原子命令。
- 锁 value 应包含用户/订单标识，释放时用 Lua 脚本校验所有权。
- 当前实现使用静态 value `'locked'`，Celery 释放时无法验证所有权。

### 退款
- `out_refund_no` 作为幂等键，重试时必须复用同一个值。
- 正常退款限流 150 QPS，错误请求限流 6 QPS。
- 必须设置 `notify_url`。
- 订单超过 1 年不能退款。

### 取消策略
- 24 小时以上全额、12-24 小时 50%、12 小时内 0% 是运动场馆常见标准。
- 当前代码使用 24h 分界，但需求描述为 2h，需业务确认。

---

## 四、下一步建议

1. **立即修复 P0 前端阻断问题**：`confirm.wxml` / `success.wxml` 必须可正常使用。
2. **立即修复 P0 后端 bug**：时区计算、回调槽位校验、Celery asyncio loop。
3. **本周内完成 P1**：付费取消入口、立即支付、订单详情、支付幂等。
4. **下周完成 P0 结算**：设计并实现微信分账调度任务和回调。
5. **更新文档**：`workflow-backend-api.md`、`功能审计报告`、`checklist.md` 中已过时的限制项。

---

## 五、已修复问题（评审后）

1. **P0-1 确认订单页空占位符**
   - 文件：`miniprogram/pages/booking/confirm.wxml`、`confirm.wxss`、`confirm.js`
   - 修复：重写确认页 UI，展示俱乐部、场地、日期、时间、时长、价格，提供「立即支付」和「取消」按钮；从 `venue-detail` 传递俱乐部/场地名称。

2. **P0-2 支付成功页空占位符**
   - 文件：`miniprogram/pages/booking/success.js`、`success.wxml`、`success.wxss`
   - 修复：加载订单详情展示支付结果，若状态仍为 `pending` 则每 3 秒轮询一次，最多 20 次；提供「查看我的预约」和「返回首页」按钮。

3. **P0-3 取消规则时区计算错误**
   - 文件：`backend/app/api/v1/bookings.py`
   - 修复：取消 `datetime.utcnow()`，改用 `Asia/Shanghai` 时区计算开场前时间，并将取消时间统一存储为 UTC naive。

4. **P0-4 支付回调未验证 slot 锁定归属**
   - 文件：`backend/app/api/v1/bookings.py`
   - 修复：在标记 `slot.status = booked` 前，检查 `slot.status == locked` 且 `slot.locked_by == order.user_id`；若锁定已失效，发送异常通知并不修改槽位状态。

5. **P0-5 Celery 任务 `asyncio.get_event_loop()` 问题**
   - 文件：`backend/app/tasks/tasks.py`
   - 修复：`release_expired_locks` 和 `generate_daily_slots` 均改为 `asyncio.run()`；锁超时时间改用 `settings.BOOKING_LOCK_TTL_SECONDS`；任务返回实际处理数量。

6. **P1-1/P1-2 前端缺少「立即支付」和付费订单「取消/退款」入口**
   - 文件：`miniprogram/pages/profile/my-bookings.js`、`my-bookings.wxml`、`my-bookings.wxss`
   - 修复：`pending` 订单显示「立即支付」；`paid` 订单显示「取消/退款」，按 24h/50% 规则预览退款金额。

7. **P1-4 重复调用 `/{id}/pay` 无幂等控制**
   - 文件：`backend/app/models/models.py`、`backend/app/schemas/schemas.py`、`backend/app/core/config.py`、`backend/app/api/v1/bookings.py`
   - 修复：`BookingOrder` 新增 `prepay_id`/`prepay_id_created_at` 字段，配置 `PREPAY_ID_TTL_SECONDS=300`，5 分钟内复用已有 `prepay_id`。

8. **P1-5 创建微信支付订单前未检查锁有效性**
   - 文件：`backend/app/api/v1/bookings.py`
   - 修复：`pay_booking` 校验 `slot.status == locked`、`locked_by == current_user`、`locked_at` 未超过 TTL。

9. **P1-6 `REFUND.CLOSED` 槽位回收状态不一致**
   - 文件：`backend/app/api/v1/bookings.py`
   - 修复：退款关闭时订单恢复为 `paid`，仅在槽位仍为 `available` 时回收为 `booked`，并设置 `locked_by=None`、`locked_at=None`，不再重新获取 Redis 锁。

10. **P1-7 未处理 `REFUND.ABNORMAL`**
    - 文件：`backend/app/api/v1/bookings.py`
    - 修复：新增 `ABNORMAL` 分支，将退款记录和订单标记为 `abnormal`，订单恢复为 `paid`，并通知用户和平台管理员人工处理。

11. **补充修复：`SettlementStatus` 未导入**
    - 文件：`backend/app/api/v1/bookings.py`
    - 修复：从 `app.models.models` 导入 `SettlementStatus` 和 `UserRole`。

12. **补充修复：`refund_status` 默认值语义错误**
    - 文件：`backend/app/models/models.py`
    - 修复：`BookingOrder.refund_status` 默认从 `"pending"` 改为 `None`（未发起退款时为空）。

## 来源引用

- [Mini Program Calls Payment - WeChat Pay](https://pay.weixin.qq.com/doc/global/v3/en/4012356546)
- [Payment Result Notification - WeChat Pay](https://pay.weixin.qq.com/doc/global/v3/en/4012356545)
- [Callback Verification - WeChat Pay](https://pay.weixin.qq.com/doc/global/v3/en/4013665320)
- [Submit Refund - WeChat Pay](https://pay.weixin.qq.com/doc/global/v2/en/4013665021)
- [SETNX - Redis Docs](https://redis.io/docs/latest/commands/setnx/)
- [Redis Booking Lock System - OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-booking-lock-system/view)
- [Cancellation Policy - Sporty Hub](https://www.sporty-hub.com/policies/cancellation)
