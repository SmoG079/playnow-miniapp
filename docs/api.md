# 接口文档

**Base URL**: `https://www.tennisplaynow.site/api/v1`

## 通用说明

### 鉴权方式

在请求头中携带 JWT Token：`Authorization: Bearer {access_token}`

### 鉴权层级

| 标记 | 说明 |
|------|------|
| 🟢 公开 | 无需 Token |
| 🟡 登录用户 | 需要有效的 access_token |
| 🔴 俱乐部管理员 | 需要 club_admin 角色 + 是该俱乐部成员 |
| ⚫ 平台超管 | 需要 platform_admin 角色 |

### 通用响应格式

**成功**：直接返回数据
```json
{ "id": 1, "name": "..." }
```

**分页列表**：
```json
{ "items": [], "total": 100, "page": 1, "page_size": 20 }
```

**错误**：
```json
{ "detail": "错误描述" }
```

---

## 1. 认证接口

### 1.1 微信登录 `POST /auth/login` 🟢
### 1.2 刷新 Token `POST /auth/refresh` 🟢

---

## 2. 用户接口

### 2.1 获取个人信息 `GET /users/me` 🟡
### 2.2 更新个人资料 `PUT /users/me` 🟡
### 2.3 我的通知列表 `GET /users/me/notifications` 🟡
### 2.4 我的预约列表 `GET /users/me/bookings` 🟡

```
?status=pending|paid|completed|cancelled&page=1&page_size=20
```

返回 `BookingDetail` 分页列表（含场地名、日期、时间段、金额、状态）。

---

## 3. 俱乐部接口

### 3.1 俱乐部列表 `GET /clubs` 🟢
### 3.2 俱乐部详情 `GET /clubs/{id}` 🟢
### 3.3 创建俱乐部 `POST /clubs` 🟡
### 3.4 编辑俱乐部 `PUT /clubs/{id}` 🔴
### 3.5 俱乐部场地列表 `GET /clubs/{id}/venues` 🟢
### 3.6 俱乐部订单列表 `GET /clubs/{id}/orders` 🔴
### 3.7 俱乐部统计 `GET /clubs/{id}/stats` 🔴

---

## 4. 场地接口

### 4.1 场地详情 `GET /venues/{id}` 🟢

返回含 `open_time`/`close_time` 营业时间。

### 4.2 创建场地 `POST /venues/with-club/{club_id}` 🔴

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 场地名称 |
| price_per_hour | decimal | 是 | 每小时价格 |
| open_time | string | 否 | 营业开始，默认 "08:00" |
| close_time | string | 否 | 营业结束，默认 "22:00" |

> 创建后自动按营业时间以 30 分钟间隔生成未来 3 天全部时段。

### 4.3 编辑场地 `PUT /venues/{id}/with-club/{club_id}` 🔴
### 4.4 删除场地 `DELETE /venues/{id}/with-club/{club_id}` 🔴

### 4.5 查询时间段 `GET /venues/{id}/slots` 🟢

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date_from | date | 是 | YYYY-MM-DD |
| date_to | date | 是 | YYYY-MM-DD |

返回按日期分组的时间段，每个 slot 含 `status`：
- `available` - 可预约
- `locked` - 锁定中（他人在支付，10 分钟超时自动释放）
- `booked` - 已预约
- `maintenance` - 维护中

> 时段价格为半小时价格（= 小时价 / 2）。查询时自动检测 Redis 锁过期并释放。

### 4.6 批量生成时间段 `POST /venues/{id}/slots/batch` 🔴

---

## 5. 预约接口

### 5.1 创建预约 `POST /bookings` 🟡

```json
{ "slot_id": 1, "slot2_id": 2 }
```

> `slot2_id` 可选，传入则同时锁定两个 30 分钟时段（= 1 小时预订）。
> 流程：Redis 分布式锁 → 更新 DB 状态为 locked → 生成 pending 订单。

### 5.2 发起支付 `POST /bookings/{id}/pay` 🟡

> **当前为占位实现**：直接标记订单为已支付 + 释放锁 + 创建分账记录 + 通知。
> 微信 JSAPI 支付待后续接入。

返回：
```json
{ "msg": "ok", "order_no": "20240614120000ABC12345", "amount": "50.00" }
```

### 5.3 预约详情 `GET /bookings/{id}` 🟡
### 5.4 取消预约 `POST /bookings/{id}/cancel` 🟡

支持 `pending` 和 `paid` 状态取消，同时释放关联的所有 locked 时段。

### 5.5 微信支付回调 `POST /bookings/wx-notify` 🟢
### 5.6 俱乐部订单 `GET /bookings/club/{club_id}` 🔴

---

## 6. 约球帖接口

### 6.1 约球帖列表 `GET /posts` 🟢

返回 `venue_id`/`booking_id` 用于区分自由约球和订场约球。

### 6.2 发布约球帖 `POST /posts` 🟡

| 字段 | 说明 |
|------|------|
| club_id | 俱乐部 ID（必填） |
| title | 标题（必填） |
| venue_id | 关联场地（订场约球时传入） |
| booking_id | 关联预约（订场约球时传入） |
| preferred_date/start/end | 约球时间 |
| players_needed | 还差几人 |
| level_required | 水平要求 |
| notes | 备注 |

### 6.3 约球帖详情 `GET /posts/{id}` 🟢

含报名列表 `registrations`。

### 6.4 报名 `POST /posts/{id}/register` 🟡
### 6.5 取消报名 `DELETE /posts/{id}/register` 🟡
### 6.6 审核报名 `PUT /posts/{id}/registrations/{user_id}` 🟡（P1，帖主功能）

---

## 7. 比赛接口

（Phase 3，后端已实现，前端待开发）

---

## 8. 通用接口

### 8.1 健康检查 `GET /health` 🟢
### 8.2 图片上传 `POST /upload` 🟡

---

## 附录：枚举值

### 时段状态 (slot status)
| 值 | 说明 |
|----|------|
| available | 可预约 |
| locked | 锁定中（10 分钟支付窗口，超时自动释放） |
| booked | 已预约 |
| maintenance | 维护/比赛锁定 |

### 订单状态 (order status)
| 值 | 说明 |
|----|------|
| pending | 待支付 |
| paid | 已支付 |
| cancelled | 已取消 |
| refunding | 退款中 |
| refunded | 已退款 |
| completed | 已完成 |
