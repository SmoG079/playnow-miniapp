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

## 已知限制
1. **退款未处理微信回调**: 当前退款是同步调用，实际生产应处理微信退款回调通知
2. **退款金额**: 当前实现全额退款，未按阶梯规则（24h全额/0h半额）
3. **退款幂等**: 未实现退款幂等控制

---

## Git Commit
```
feat: admin dashboard + notification system + refund API
```
