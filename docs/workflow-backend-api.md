# Workflow: 后端 API 补充实现

## 任务概览
- **目标**: 补充缺失的后端 API，修复已知问题
- **执行者**: Claude Code
- **验收者**: Hermes (Kimi)
- **优先级**: 🔴 高
- **状态**: ✅ 已完成

---

## 执行记录

### 2025-06-12 执行日志

| 时间 | 执行者 | 操作 | 状态 |
|------|--------|------|------|
| 10:15 | Claude | 实现消息通知 API (4个接口) | ✅ |
| 10:18 | Claude | 实现微信退款 API | ✅ |
| 10:20 | Claude | 修复 getUserProfile 废弃问题 | ✅ |
| 10:21 | Hermes | Git commit | ✅ |

---

## Feature 1: 消息通知 API ✅

### 实现内容
在 `backend/app/api/v1/users.py` 添加 4 个接口：

```python
GET  /users/me/notifications/{id}          # 消息详情
PUT  /users/me/notifications/{id}/read     # 标记已读
PUT  /users/me/notifications/read-all      # 全部已读
GET  /users/me/notifications/unread-count  # 未读数
```

### 代码变更
- `users.py`: 添加 4 个 endpoint，使用 `update()` 批量更新未读状态
- 导入 `update` from sqlalchemy
- 仅操作当前用户的消息（`user_id == current_user.id`）

---

## Feature 2: 微信退款 API ✅

### 实现内容
在 `backend/app/api/v1/bookings.py` 添加：

```python
POST /bookings/{id}/refund
```

### 代码变更
- `bookings.py`: 
  - 添加 `refund_booking` endpoint
  - 仅 `paid` 状态的订单可退款
  - 调用 `wechatpayv3.refund()` 进行全额退款
  - 更新订单状态为 `refunded`
  - 释放场地时段
  - 创建退款通知
- `schemas.py`: 添加 `RefundRequest` schema

### 退款流程
1. 用户/管理员请求退款
2. 校验订单状态为 `paid`
3. 调用微信支付退款 API
4. 更新订单状态 → `refunded`
5. 释放场地时段
6. 创建退款成功通知

---

## Feature 3: 修复 getUserProfile 废弃问题 ✅

### 问题
`wx.getUserProfile` 已被微信废弃回收。

### 解决方案
- 移除 `miniprogram/utils/auth.js` 中的 `getWechatUserProfile` 函数
- 前端已使用 `<button open-type="chooseAvatar">` 和 `<input type="nickname">`
- 更新 module.exports

---

## 文件变更清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/app/api/v1/users.py` | 修改 | 添加 4 个通知 API |
| `backend/app/api/v1/bookings.py` | 修改 | 添加退款 API |
| `backend/app/schemas/schemas.py` | 修改 | 添加 RefundRequest schema |
| `miniprogram/utils/auth.js` | 修改 | 移除废弃函数 |

---

## 验收标准
- [x] 消息详情 API 返回正确数据
- [x] 标记已读后数据库更新
- [x] 未读数 API 返回正确计数
- [x] 退款 API 调用微信支付
- [x] 取消已支付订单触发退款
- [x] 移除废弃的 getUserProfile
- [x] 所有 Python 文件语法正确

---

## 当前 Booking & Payment 流程（已更新）

### 核心端点
```python
POST /bookings                      # 锁定时段并创建待支付订单
POST /bookings/{id}/pay             # 创建/复用微信支付 prepay_id
POST /bookings/wx-notify            # 微信回调入口（验签 -> 解密 -> 入队 Celery）
POST /bookings/{id}/cancel          # 用户取消（pending 直接取消；paid 按阶梯退款）
POST /bookings/{id}/refund          # 管理员/用户主动退款
GET  /bookings/config               # 获取 free_cancel_hours 等配置
```

### 支付流程
1. 用户选时段 → `POST /bookings`：SELECT FOR UPDATE + Redis 锁 → slot `locked`
2. 用户支付 → `POST /bookings/{id}/pay`：复用有效期内 prepay_id，返回 JSAPI 参数
3. 微信支付回调 → `POST /bookings/wx-notify`：验签、解密、nonce 去重、立即 SUCCESS，Celery 异步处理
4. Celery `process_wx_callback`：更新订单 `paid`、释放 Redis 锁、创建结算记录、写通知

### 退款流程
1. 用户取消已支付订单 → `POST /bookings/{id}/cancel`
2. 后端按 `FREE_CANCEL_HOURS` 计算退款比例（≥N 小时全额，0-N 小时 50%，<0 不可退）
3. 预创建 `RefundRecord` → 调用 `wxpay.refund()` → 订单进入 `refunding`
4. 微信 `REFUND.*` 回调 → Celery 更新 `RefundRecord` 和订单状态
5. 失败退款由 Celery `retry_failed_refunds` / `poll_processing_refunds` 轮询/重试

### 结算流程
1. 支付成功后创建 `SettlementRecord`（状态 `pending`，scheduled_at = payment_time + 30 天）
2. Celery `execute_pending_settlements` 到期调用微信分账
3. 分账成功后调用 `profitsharing_unfreeze` 解冻剩余资金
4. `query_settlement_status` 轮询 `PROCESSING` 状态至 terminal

---

## 已实现的增强
- 回调安全：先验签再解密，时间戳校验（±60s），nonce Redis `SET NX EX` 去重
- 金额校验：回调金额与订单金额比对（`_to_cents` 精确转换）
- Redis 锁：Lua 脚本原子释放，锁 value 为 user_id
- 幂等：prepay_id 复用、退款 `out_refund_no` 唯一、回调状态机保护
- 限流：`/pay`、`/cancel`、`/refund` 按用户 Redis Lua 原子限流
- 时区：模块内统一 UTC naive，业务计算显式转 Asia/Shanghai
- 异步：所有回调处理、结算、退款重试均走 Celery

---

## 已知限制
1. **club-detail 页面已移除**：当前俱乐部详情/预订入口统一为 `venue-detail`（club-list 点击跳转）
2. **club-list / venue-detail 命名**：历史命名未统一，不影响功能
3. **文档同步**：本文件已随 2026-06-15 修复同步；若后续 API 变更需继续更新

---

## 最近相关 Commit
```
hotfix: restore missing sqlalchemy imports in Celery tasks
fix: add missing db.commit in generate_slots and remove dead code in update_slot_status
fix: frontend auth/request blockers - accept 2xx and prevent refresh infinite loop
fix: atomic nonce replay protection and explicit commit in create_booking
fix: four backend issues in tasks, settlement, and payment callback
fix: add onShow login guard to confirm.js and fix my-bookings refund timezone bug
fix: timer leaks, login guard, error state, and wxpay validation
fix: remove stray db.commit from process_callback for unhandled events
fix: club-list pagination and remove dead club-detail page
fix: add missing route decorator for refund_booking
```
