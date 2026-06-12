# Workflow: 后端 API 补充实现

## 任务概览
- **目标**: 补充缺失的后端 API，修复已知问题
- **执行者**: Claude Code
- **验收者**: Hermes (Kimi)
- **优先级**: 🔴 高

---

## Feature 1: 消息通知 API ✅

### 需求
补充 `users.py` 中缺失的消息通知接口：

```python
GET  /users/me/notifications/{id}          # 消息详情
PUT  /users/me/notifications/{id}/read     # 标记已读
PUT  /users/me/notifications/read-all      # 全部已读
GET  /users/me/notifications/unread-count  # 未读数
```

### 实现要求
- 使用现有 `Notification` 模型
- 返回 `NotificationBrief` schema
- 仅操作当前用户的消息（`user_id == current_user.id`）

---

## Feature 2: 微信退款 API 🔴

### 需求
实现 `POST /bookings/{id}/refund`，在取消已支付订单时调用微信退款。

### 实现要求
- 仅 `paid` 状态的订单可退款
- 调用 `wechatpayv3.refund()`
- 更新订单状态为 `refunded`
- 创建退款通知

---

## Feature 3: 修复 getUserProfile 废弃问题 🟡

### 需求
`wx.getUserProfile` 已废弃，需改用新方式获取用户信息。

### 实现要求
- 前端改用 `<button open-type="chooseAvatar">` 和 `<input type="nickname">`
- 后端接收头像 URL 和昵称保存
- 移除 `utils/auth.js` 中的 `getUserProfile`

---

## 执行步骤

### Step 1: 消息通知 API
1. 在 `backend/app/api/v1/users.py` 添加 4 个接口
2. 检查 `schemas.py` 是否有需要的 schema
3. 语法检查

### Step 2: 微信退款
1. 在 `backend/app/api/v1/bookings.py` 添加 `POST /{id}/refund`
2. 在 `wechat_pay.py` 添加 `refund()` 方法
3. 修改 `cancel_booking` 逻辑，已支付订单走退款流程

### Step 3: 修复 getUserProfile
1. 修改 `miniprogram/utils/auth.js`
2. 检查 `login.wxml` 是否已使用新方式
3. 语法检查

---

## 验收标准
- [ ] 消息详情 API 返回正确数据
- [ ] 标记已读后数据库更新
- [ ] 未读数 API 返回正确计数
- [ ] 退款 API 调用微信支付
- [ ] 取消已支付订单触发退款
- [ ] 移除废弃的 getUserProfile
- [ ] 所有 Python 文件语法正确
