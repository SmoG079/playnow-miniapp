# 模块 B（预约 & 支付）修复进度跟踪

## 状态图例
- ✅ 已完成
- 🔄 进行中
- ⏳ 待开始
- ❓ 需确认

---

## P0 阻断级问题

| # | 问题 | 状态 | 负责人 | 备注 |
|---|------|------|--------|------|
| P0-1 | TOCTOU 竞态：create_booking 先检查 slot 状态再获取 Redis 锁 | ✅ | Claude | 已使用 SELECT FOR UPDATE |
| P0-2 | Redis 锁在 DB 事务外获取 | ✅ | Claude | 已移入 try 块 |
| P0-3 | Decimal 转 cents 截断 | ✅ | Claude | 已使用 _to_cents |
| P0-4 | 回调签名验证顺序错误（先解析再验签） | ✅ | Claude | 已先 decrypt_callback |
| P0-5 | 回调处理重工作阻塞响应（>5s） | ✅ | Claude | 已改为 Celery 异步 |
| P0-6 | 无时间戳/重放保护 | ✅ | Claude | 已添加 nonce/timestamp 检查 |
| P0-7 | 回调未校验金额 | ✅ | Claude | 已校验 amount.total |
| P0-8 | release_expired_locks 无所有权校验释放 Redis 锁 | ✅ | Claude | 已传 slot.locked_by |
| P0-9 | app.js request() 拒绝 201 Created | ✅ | Claude | 已接受 2xx |
| P0-10 | refreshTokenAndRetry 无限递归 | ✅ | Claude | 已加 skipRefresh |
| P0-11 | confirm.js 无登录守卫 | ✅ | Claude | 已加 requireLogin |
| P0-12 | wxpay.js 无参数校验直接调用 requestPayment | ✅ | Claude | 已加 validatePayParams |
| P0-1 (旧) | 确认订单页 confirm.wxml 是占位符 | ✅ | Claude | 重写 confirm.wxml/wxss |
| P0-2 (旧) | 支付成功页 success.wxml 是占位符 | ✅ | Claude | 重写 success.js/wxml/wxss |
| P0-3 (旧) | 取消规则时区计算错误 | ✅ | Claude | 使用 Asia/Shanghai 时区 |
| P0-4 (旧) | 支付回调未验证 slot 锁定归属 | ✅ | Claude | 回调中校验 slot 状态 |
| P0-5 (旧) | Celery 任务 asyncio.get_event_loop() 问题 | ✅ | Claude | 改为 asyncio.run() |
| P0-6 (旧) | 结算（分账）执行完全缺失 | ✅ | Claude | 新增 SettlementRecord 字段、Celery 任务、分账 API |

## P1 高优先级问题

| # | 问题 | 状态 | 负责人 | 备注 |
|---|------|------|--------|------|
| P1-1 | 时区一致性：系统混用 UTC naive / aware / Asia/Shanghai | ✅ | Claude | 统一使用 UTC naive 存储，显式转换计算 |
| P1-2 | create_booking 未校验 slot 是否在未来 | ✅ | Claude | 已添加过去时间校验 |
| P1-3 | Celery asyncio.run 创建新事件循环 | ✅ | Claude | 已改用 asgiref.async_to_sync |
| P1-4 | 退款回调幂等性缺口 | ✅ | Claude | payment_callback.py 已加状态检查 |
| P1-5 | 分账 unfreeze_unsplit=True 无条件 | ✅ | Claude | 改为分账成功后显式解冻 |
| P1-6 | 分账 receiver sum 调整未同步 DB 字段 | ✅ | Claude | 调整后同步 Decimal 字段 |
| P1-7 | 无速率限制（pay/cancel/refund） | ✅ | Claude | 新增 Redis Lua 原子限流 |
| P1-8 | success.js 成功图标对所有非 pending 状态显示 | ✅ | Claude | 按状态显示不同图标/文案 |
| P1-9 | confirm.js 无支付倒计时 | ✅ | Claude | 添加倒计时和过期禁用 |
| P1-10 | my-bookings 硬编码 24h 退款阈值 | ✅ | Claude | 从 /bookings/config 读取 |
| P1-11 | my-bookings 通过 data-booking 传递完整对象 | ✅ | Claude | 改为 data-id + 列表查找 |
| P1-12 | RefundRecord 缺少 updated_at 但任务查询它 | ✅ | Claude | 模型已存在 updated_at |
| P1-1 (旧) | 前端缺少付费订单取消/退款入口 | ✅ | Claude | my-bookings 对 paid 状态显示取消/退款 |
| P1-2 (旧) | 前端缺少「立即支付」按钮 | ✅ | Claude | my-bookings 对 pending 状态显示立即支付 |
| P1-4 (旧) | 重复调用 /{id}/pay 无幂等控制 | ✅ | Claude | 新增 prepay_id/prepay_id_created_at |
| P1-5 (旧) | 创建微信支付订单前未检查锁有效性 | ✅ | Claude | 检查 slot.status/locked_by/locked_at |
| P1-6 (旧) | REFUND.CLOSED 槽位回收状态不一致 | ✅ | Claude | 回收为 booked 且 locked_by=None |
| P1-7 (旧) | 未处理 REFUND.ABNORMAL | ✅ | Claude | 增加 ABNORMAL 分支 |
| P1-8 (旧) | 退款重试机制缺失 | ✅ | Claude | 新增 refund retry 字段、Celery 任务 |

## P2 中优先级问题

| # | 问题 | 状态 | 负责人 | 备注 |
|---|------|------|--------|------|
| P2-1 | BookingOrder.order_no 缺少索引 | ✅ | Claude | `models.py:168` 已加 index |
| P2-2 | refund_status 未使用 Enum | ✅ | Claude | 已改为 Enum(RefundStatus, native_enum=False) |
| P2-3 | _refund_slot_release 死代码 | ✅ | Claude | 已删除 |
| P2-4 | update_slot_status 死/不可达代码 | ✅ | Claude | `venues.py:240-252` 已改为 PATCH 端点 |
| P2-5 | venue-detail 网格未区分 locked/booked 视觉状态 | ✅ | Claude | 已区分样式 |
| P2-6 | club-list 缺少 onReachBottom 分页 | ✅ | Claude | 已添加分页（bf0ae26） |
| P2-7 | club-detail 是空占位符 | ✅ | Claude | 已移除空页面及 app.json 注册（bf0ae26） |
| P2-8 | venue-detail/club-list 导航命名混乱 | ✅ | Claude | 已添加注释说明（bf0ae26） |
| P2-9 | 文档与实现不同步 | ✅ | Claude | 已同步 workflow-backend-api.md（319726f） |

---

## 变更日志

### 2026-06-15
- 完成所有 P1 高优先级问题修复（时区统一、未来时段校验、Celery async_to_sync、分账解冻条件、receiver sum 同步、速率限制、成功页状态 UI、确认页倒计时、动态退款阈值、data-id 传参）
- 开展模块 B 上线前评审，发现并修复阻塞级问题：
  - Celery 任务缺少 `select`/`update` 导入导致所有异步任务失败（含时段生成）
  - `generate_slots` 接口未提交事务
  - `update_slot_status` 死代码
  - `utils/request.js` 拒绝 201
  - `app.js` 刷新重试无限递归
  - 回调 nonce 去重竞态
  - `create_booking` 未显式提交
  - 退款回调 slot 释放未校验所有权
  - 退款重试状态机不完善
  - 前端计时器泄漏、`success.js` 登录守卫缺失
- 修复上线前评审剩余问题：
  - `club_orders` 状态过滤字符串 → OrderStatus 枚举
  - `release_expired_locks` DB 层按 locked_at 过滤
- 完成部分 P2 优化：
  - `BookingOrder.order_no` 添加索引
  - `refund_status` / `RefundRecord.status` 改为 Enum
  - 删除 `_refund_slot_release` 死代码
  - `venue-detail` 区分 booked/locked 视觉状态
- 本轮复查新增修复：
  - `refund_booking` 添加缺失的路由装饰器
  - `club-list` 添加 `onReachBottom` 分页
  - 移除空 `club-detail` 页面及 `app.json` 注册
  - 同步 `docs/workflow-backend-api.md` 至当前实现
- 31 项后端测试全部通过
- 更新 `docs/module-b-production-readiness.md` 和 `docs/module-b-fix-progress.md`

### 2026-06-13 (fix-null-nicknames)
- 修复用户昵称/头像/手机号为空的问题：
  - 后端 `User` 模型新增 `session_key` 字段，用于服务端解密手机号
  - 登录接口 `wx_login` 现在保存/更新 `session_key`
  - 新增服务端手机号获取接口 `/auth/phone`：通过缓存的 `access_token` 调用微信 `getuserphonenumber` API，将 `purePhoneNumber` 存入用户资料
  - `UserUpdate`  schema 和 `PUT /users/me` 支持更新 `phone` 字段
  - 前端登录页 `login.js`/`login.wxml`：收集昵称和头像，登录后自动同步到后端；手机号授权改为直接调用 `/auth/phone` 服务端接口

### 2026-06-13
- 创建 `docs/module-b-review-report.md` 和 `docs/module-b-fix-progress.md`
- 完成多 Agent 评审和外部参考研究
- 修复 P0/P1 问题：确认页、成功页、我的预约支付/退款、支付幂等、锁校验、退款回调异常处理、Celery asyncio
- 修复 P0-6 结算执行：新增 `SettlementRecord` 字段、`execute_pending_settlements` Celery 任务、微信分账 API、管理员结算接口
- 修复 P1-8 退款重试：新增 `RefundRecord` 重试字段、退款记录预创建、`retry_failed_refunds` / `poll_processing_refunds` Celery 任务
- 修复报名/评论登录前置检查：`post-detail.js` 中报名、取消报名、评论、删除评论、打开群聊前调用 `app.requireLogin()`；`login.js` 支持登录后跳回原始页面
