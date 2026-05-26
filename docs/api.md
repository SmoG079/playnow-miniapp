# PlayNow API 文档

Base URL: `https://www.tennisplaynow.site/api/v1`

## 目录

- [1. 认证接口](#1-认证接口)
- [2. 用户接口](#2-用户接口)
- [3. 俱乐部接口](#3-俱乐部接口)
- [4. 场地接口](#4-场地接口)
- [5. 预约接口](#5-预约接口)
- [6. 约球帖接口](#6-约球帖接口)
- [7. 比赛接口](#7-比赛接口)
- [8. 通用接口](#8-通用接口)
- [附录：枚举值](#附录枚举值)

---

## 通用说明

### 鉴权方式

在请求头中携带 JWT Token：

```
Authorization: Bearer {access_token}
```

| 鉴权层级 | 标记 | 说明 |
|----------|------|------|
| 公开 | 🟢 | 无需 Token |
| 登录用户 | 🟡 | 需要有效的 access_token |
| 俱乐部管理员 | 🔴 | 需要 club_admin 角色 + 是该俱乐部成员 |
| 平台超管 | ⚫ | 需要 platform_admin 角色 |

### 通用响应格式

**成功**:
```json
{
  // 直接返回数据
}
```

**分页列表**:
```json
{
  "items": [],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

**错误**:
```json
{
  "detail": "错误描述"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未登录或 Token 过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突（如重复预约） |
| 422 | 请求体校验失败 |

---

## 1. 认证接口

### 1.1 微信登录

> 🟢 公开

```
POST /auth/login
```

**请求体**:
```json
{
  "code": "微信 wx.login() 返回的 code"
}
```

**响应**:
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

access_token 有效期 2 小时，refresh_token 有效期 7 天。首次登录自动创建用户。

---

### 1.2 刷新 Token

> 🟢 公开

```
POST /auth/refresh
```

**请求体**:
```json
{
  "refresh_token": "eyJhbGciOi..."
}
```

**响应**:
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

返回新的 access_token 和 refresh_token。

---

## 2. 用户接口

### 2.1 获取个人信息

> 🟡 登录用户

```
GET /users/me
```

**响应**:
```json
{
  "id": 1,
  "nickname": "张三",
  "avatar_url": "https://oss.example.com/avatars/1.png",
  "phone": "13800138000",
  "role": "user",
  "created_at": "2024-01-01T00:00:00",
  "managed_club_ids": []
}
```

`role` 可能的值: `user` | `club_admin` | `platform_admin`
`managed_club_ids` 为用户管理的俱乐部 ID 列表。

---

### 2.2 更新个人资料

> 🟡 登录用户

```
PUT /users/me
```

**请求体**:
```json
{
  "nickname": "新昵称",
  "avatar_url": "https://oss.example.com/avatars/1.png"
}
```

---

### 2.3 我的通知列表

> 🟡 登录用户

```
GET /users/me/notifications?page=1&page_size=20
```

**响应**:
```json
{
  "items": [
    {
      "id": 1,
      "type": "booking",
      "title": "预约成功",
      "content": "您的场地预约已支付成功，订单号 20240101120000ABC12345",
      "ref_id": 1,
      "ref_type": "booking",
      "is_read": false,
      "created_at": "2024-01-01T12:00:00"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

---

## 3. 俱乐部接口

### 3.1 俱乐部列表

> 🟢 公开

```
GET /clubs?lat=30.5&lng=120.5&sport=badminton&keyword=羽毛球&page=1&page_size=20
```

**查询参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| lat | float | 否 | 用户纬度（用于附近排序） |
| lng | float | 否 | 用户经度 |
| sport | string | 否 | 运动类型筛选，如 `badminton` |
| keyword | string | 否 | 名称搜索关键词 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，最大 50 |

**响应**: 分页列表，每项为：
```json
{
  "id": 1,
  "name": "羽你同行俱乐部",
  "sport_types": ["badminton", "basketball"],
  "cover_image": "https://oss.example.com/clubs/1/cover.png",
  "address": "北京市朝阳区xxx路100号",
  "latitude": 39.9042,
  "longitude": 116.4074,
  "status": "active"
}
```

---

### 3.2 俱乐部详情

> 🟢 公开

```
GET /clubs/{club_id}
```

**响应**:
```json
{
  "id": 1,
  "name": "羽你同行俱乐部",
  "sport_types": ["badminton", "basketball"],
  "description": "北京最专业的羽毛球俱乐部",
  "cover_image": "https://oss.example.com/clubs/1/cover.png",
  "images": ["https://oss.example.com/clubs/1/1.png"],
  "address": "北京市朝阳区xxx路100号",
  "latitude": 39.9042,
  "longitude": 116.4074,
  "contact_phone": "13800138000",
  "status": "active",
  "created_at": "2024-01-01T00:00:00",
  "venues": [
    {
      "id": 1,
      "club_id": 1,
      "name": "1号羽毛球场",
      "sport_type": "badminton",
      "price_per_hour": 80.00,
      "max_capacity": 4,
      "status": "active"
    }
  ]
}
```

---

### 3.3 创建俱乐部

> 🟡 登录用户（创建后自动成为 club_admin）

```
POST /clubs
```

**请求体**:
```json
{
  "name": "羽你同行俱乐部",
  "sport_types": ["badminton", "basketball"],
  "description": "北京最专业的羽毛球俱乐部",
  "cover_image": "https://oss.example.com/clubs/1/cover.png",
  "images": ["https://oss.example.com/clubs/1/1.png"],
  "address": "北京市朝阳区xxx路100号",
  "latitude": 39.9042,
  "longitude": 116.4074,
  "contact_phone": "13800138000"
}
```

**字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 俱乐部名称，1-128 字符 |
| sport_types | string[] | 否 | 运动类型列表，如 `["badminton","basketball"]` |
| description | string | 否 | 俱乐部介绍 |
| cover_image | string | 否 | 封面图 URL |
| images | string[] | 否 | 多图 URL 列表 |
| address | string | 否 | 地址 |
| latitude | decimal | 否 | 纬度（地图选点） |
| longitude | decimal | 否 | 经度（地图选点） |
| contact_phone | string | 否 | 联系电话 |

---

### 3.4 编辑俱乐部

> 🔴 俱乐部管理员

```
PUT /clubs/{club_id}
```

请求体字段同 [3.3 创建俱乐部](#33-创建俱乐部)，所有字段可选。

---

### 3.5 俱乐部场地列表

> 🟢 公开

```
GET /clubs/{club_id}/venues
```

**响应**: 场地对象数组，参见 [场地详情](#41-场地详情)。

---

### 3.6 俱乐部订单列表

> 🔴 俱乐部管理员

```
GET /clubs/{club_id}/orders?status=paid&page=1&page_size=20
```

**响应**: 分页列表，每项为 [预约详情](#53-预约详情)。

---

### 3.7 俱乐部统计概览

> 🔴 俱乐部管理员

```
GET /clubs/{club_id}/stats
```

**响应**:
```json
{
  "total_venues": 4,
  "total_orders": 256,
  "total_revenue": 51200.00,
  "venue_utilization": 72.5,
  "today_orders": 12,
  "today_revenue": 2400.00
}
```

---

## 4. 场地接口

### 4.1 场地详情

> 🟢 公开

```
GET /venues/{venue_id}
```

**响应**:
```json
{
  "id": 1,
  "club_id": 1,
  "name": "1号羽毛球场",
  "sport_type": "badminton",
  "price_per_hour": 80.00,
  "max_capacity": 4,
  "cover_image": "https://oss.example.com/venues/1.png",
  "status": "active",
  "sort_order": 0,
  "created_at": "2024-01-01T00:00:00"
}
```

---

### 4.2 创建场地

> 🔴 俱乐部管理员

```
POST /venues/with-club/{club_id}
```

**请求体**:
```json
{
  "name": "1号羽毛球场",
  "sport_type": "badminton",
  "price_per_hour": 80.00,
  "max_capacity": 4,
  "cover_image": "https://oss.example.com/venues/1.png",
  "sort_order": 0
}
```

---

### 4.3 编辑场地

> 🔴 俱乐部管理员

```
PUT /venues/{venue_id}/with-club/{club_id}
```

请求体字段同 [4.2 创建场地](#42-创建场地)，所有字段可选。可通过 `status` 字段设置场地状态。

---

### 4.4 删除（关闭）场地

> 🔴 俱乐部管理员

```
DELETE /venues/{venue_id}/with-club/{club_id}
```

软删除，将场地状态设为 `closed`。

---

### 4.5 查询时间段

> 🟢 公开

```
GET /venues/{venue_id}/slots?date_from=2024-01-01&date_to=2024-01-14
```

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date_from | date | 是 | 开始日期，格式 `YYYY-MM-DD` |
| date_to | date | 是 | 结束日期，格式 `YYYY-MM-DD` |

**响应**:
```json
[
  {
    "date": "2024-01-01",
    "slots": [
      {
        "id": 1,
        "venue_id": 1,
        "date": "2024-01-01",
        "start_time": "08:00",
        "end_time": "09:00",
        "price": 80.00,
        "status": "available"
      },
      {
        "id": 2,
        "venue_id": 1,
        "date": "2024-01-01",
        "start_time": "09:00",
        "end_time": "10:00",
        "price": 80.00,
        "status": "booked"
      }
    ]
  }
]
```

**时段状态**: `available` 可预约 | `locked` 锁定中(他人正在支付) | `booked` 已预约 | `maintenance` 维护中

---

### 4.6 批量生成时间段

> 🔴 俱乐部管理员

```
POST /venues/{venue_id}/slots/batch
```

**请求体**:
```json
{
  "date_from": "2024-01-01",
  "date_to": "2024-01-14",
  "start_time": "08:00",
  "end_time": "22:00",
  "interval_minutes": 60
}
```

**说明**: 为指定日期范围内按间隔生成时间段。已存在的时间段会跳过，不会重复创建。

**响应**:
```json
{
  "created": 196,
  "msg": "Generated 196 slots"
}
```

---

## 5. 预约接口

### 5.1 创建预约（锁场）

> 🟡 登录用户

```
POST /bookings
```

**请求体**:
```json
{
  "slot_id": 123
}
```

**流程**: 校验时段可用 → Redis 分布式锁(10分钟) → 更新 DB 状态为 `locked` → 生成 pending 订单。

**响应**: 参见 [5.3 预约详情](#53-预约详情)，`status` 为 `pending`。

**错误**:
- `409` - 时段已被预约或正在锁定中

---

### 5.2 发起支付

> 🟡 登录用户

```
POST /bookings/{booking_id}/pay
```

**响应**（用于 `wx.requestPayment`）:
```json
{
  "timeStamp": "1704067200",
  "nonceStr": "abc123def456",
  "package": "prepay_id=wx1234567890abcdef",
  "signType": "RSA",
  "paySign": "签名值..."
}
```

前端拿到后直接调用：
```javascript
wx.requestPayment({
  timeStamp: res.timeStamp,
  nonceStr: res.nonceStr,
  package: res.package,
  signType: res.signType,
  paySign: res.paySign,
  success: () => { /* 支付成功 */ },
  fail: () => { /* 支付失败或取消 */ }
});
```

---

### 5.3 预约详情

> 🟡 登录用户（只能看自己的，club_admin 可看本俱乐部所有）

```
GET /bookings/{booking_id}
```

**响应**:
```json
{
  "id": 1,
  "order_no": "20240101120000ABC12345",
  "user_id": 1,
  "venue_id": 1,
  "slot_id": 123,
  "club_id": 1,
  "amount": 80.00,
  "status": "paid",
  "payment_time": "2024-01-01T12:05:00",
  "wx_transaction_id": "4200001234567890",
  "cancel_reason": null,
  "cancel_time": null,
  "created_at": "2024-01-01T12:00:00",
  "venue_name": "1号羽毛球场",
  "club_name": "羽你同行俱乐部",
  "slot_date": "2024-01-03",
  "slot_start": "14:00",
  "slot_end": "15:00"
}
```

---

### 5.4 取消预约

> 🟡 登录用户（只能取消自己的）

```
POST /bookings/{booking_id}/cancel
```

**请求体**:
```json
{
  "reason": "临时有事"
}
```

**取消规则**:

| 时间条件 | 退款比例 |
|----------|----------|
| 开场前 ≥ 2 小时 | 全额退款 |
| 开场前 < 2 小时 | 退款 50% |
| 已开场 | 不可取消 |

**响应**:
```json
{
  "msg": "ok",
  "refund_amount": "80.00"
}
```

---

### 5.5 微信支付回调

> 🟢 公开（微信服务器调用，验签）

```
POST /bookings/wx-notify
```

此接口由微信支付系统回调，无需手动调用。

**内部处理流程**:
1. 验签
2. 幂等性检查（已 paid 则直接返回成功）
3. 更新订单状态 → `paid`
4. 更新时段状态 → `booked`
5. 释放 Redis 锁
6. 创建分账记录（SettlementRecord）
7. 创建用户通知

---

## 6. 约球帖接口

### 6.1 约球帖列表

> 🟢 公开

```
GET /posts?club_id=1&sport=badminton&status=open&page=1&page_size=20
```

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| club_id | int | 否 | 按俱乐部筛选 |
| sport | string | 否 | 运动类型筛选 |
| status | string | 否 | 状态: `open`/`closed`/`full` |
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页数量 |

**响应**: 分页列表，每项为：
```json
{
  "id": 1,
  "club_id": 1,
  "user_id": 1,
  "title": "周末来打羽毛球！3缺1",
  "sport_type": "badminton",
  "preferred_date": "2024-01-06",
  "preferred_start": "14:00",
  "preferred_end": "16:00",
  "players_needed": 1,
  "level_required": "中级",
  "status": "open",
  "created_at": "2024-01-01T12:00:00",
  "user_nickname": "张三",
  "user_avatar": "https://oss.example.com/avatars/1.png",
  "club_name": "羽你同行俱乐部",
  "registration_count": 2
}
```

---

### 6.2 发布约球帖

> 🟡 登录用户

```
POST /posts
```

**请求体**:
```json
{
  "club_id": 1,
  "title": "周末来打羽毛球！3缺1",
  "sport_type": "badminton",
  "preferred_date": "2024-01-06",
  "preferred_start": "14:00",
  "preferred_end": "16:00",
  "players_needed": 1,
  "level_required": "中级",
  "notes": "自带球拍，场地费AA",
  "venue_id": null,
  "booking_id": null
}
```

**两种模式**:
- **自由约球**: `venue_id` 和 `booking_id` 为空，不关联场地预约
- **订场约球**: 填写 `venue_id` 和 `booking_id`，关联已有预约

---

### 6.3 约球帖详情

> 🟢 公开

```
GET /posts/{post_id}
```

**响应**: 在列表项基础上增加：
```json
{
  "notes": "自带球拍，场地费AA",
  "venue_id": null,
  "booking_id": null,
  "registrations": [
    {
      "id": 1,
      "user_id": 2,
      "message": "我水平一般，求带！",
      "status": "pending",
      "user_nickname": "李四",
      "user_avatar": "https://oss.example.com/avatars/2.png"
    }
  ]
}
```

---

### 6.4 报名约球

> 🟡 登录用户

```
POST /posts/{post_id}/register
```

**请求体**:
```json
{
  "message": "我水平一般，求带！"
}
```

报名后系统自动通知帖主。

---

### 6.5 取消报名

> 🟡 登录用户（只能取消自己的）

```
DELETE /posts/{post_id}/register
```

---

### 6.6 审核报名

> 🟡 登录用户（仅帖主）

```
PUT /posts/{post_id}/registrations/{user_id}
```

**请求体**:
```json
{
  "status": "approved"
}
```

`status` 可选值: `approved` 通过 | `rejected` 拒绝

---

## 7. 比赛接口

### 7.1 比赛列表

> 🟢 公开

```
GET /tournaments?club_id=1&sport=badminton&status=open&page=1&page_size=20
```

**查询参数**: 同 [6.1 约球帖列表](#61-约球帖列表)。

**响应**: 分页列表，每项为：
```json
{
  "id": 1,
  "club_id": 1,
  "title": "2024元旦羽毛球公开赛",
  "sport_type": "badminton",
  "start_time": "2024-01-01T09:00:00",
  "end_time": "2024-01-01T18:00:00",
  "venue_id": 1,
  "entry_fee": 50.00,
  "max_participants": 32,
  "current_participants": 20,
  "cover_image": "https://oss.example.com/tournaments/1.png",
  "status": "open",
  "created_at": "2023-12-01T00:00:00",
  "club_name": "羽你同行俱乐部"
}
```

---

### 7.2 创建比赛

> 🔴 俱乐部管理员

```
POST /tournaments
```

**请求体**:
```json
{
  "club_id": 1,
  "title": "2024元旦羽毛球公开赛",
  "description": "年度大赛，欢迎报名",
  "sport_type": "badminton",
  "start_time": "2024-01-01T09:00:00",
  "end_time": "2024-01-01T18:00:00",
  "venue_id": 1,
  "lock_venue": true,
  "max_participants": 32,
  "entry_fee": 50.00,
  "cover_image": "https://oss.example.com/tournaments/1.png"
}
```

**`lock_venue` 说明**: 设为 `true` 时，比赛时段内关联场地的所有时间段自动设为 `maintenance` 状态，禁止普通预约。

---

### 7.3 比赛详情

> 🟢 公开

```
GET /tournaments/{tournament_id}
```

**响应**: 在列表项基础上增加：
```json
{
  "description": "年度大赛，欢迎报名",
  "lock_venue": true,
  "registrations": [
    {
      "id": 1,
      "user_id": 2,
      "status": "registered",
      "user_nickname": "李四",
      "user_avatar": "https://oss.example.com/avatars/2.png"
    }
  ]
}
```

---

### 7.4 编辑比赛

> 🔴 俱乐部管理员

```
PUT /tournaments/{tournament_id}
```

请求体字段同 [7.2 创建比赛](#72-创建比赛)，所有字段可选。可通过 `status` 切换比赛状态。

---

### 7.5 报名比赛

> 🟡 登录用户

```
POST /tournaments/{tournament_id}/register
```

**注意**:
- 比赛必须处于 `open` 状态
- 名额已满时返回 400
- 如报名费 > 0，需走支付流程（TODO）

---

## 8. 通用接口

### 8.1 图片上传

> 🟡 登录用户

```
POST /upload
Content-Type: multipart/form-data

file: (binary)
```

**响应**:
```json
{
  "url": "https://oss.example.com/uploads/abc123.png",
  "filename": "abc123.png"
}
```

---

### 8.2 健康检查

> 🟢 公开

```
GET /health
```

**响应**:
```json
{
  "status": "ok"
}
```

---

## 附录：枚举值

### 用户角色 (role)

| 值 | 说明 |
|----|------|
| `user` | 普通用户 |
| `club_admin` | 俱乐部管理员 |
| `platform_admin` | 平台超管 |

### 场地状态 (venue status)

| 值 | 说明 |
|----|------|
| `active` | 营业中 |
| `maintenance` | 维护中 |
| `closed` | 已关闭 |

### 时段状态 (slot status)

| 值 | 说明 |
|----|------|
| `available` | 可预约 |
| `locked` | 锁定中（他人在支付） |
| `booked` | 已预约 |
| `maintenance` | 维护/比赛锁定 |

### 订单状态 (order status)

| 值 | 说明 |
|----|------|
| `pending` | 待支付 |
| `paid` | 已支付 |
| `cancelled` | 已取消 |
| `refunding` | 退款中 |
| `refunded` | 已退款 |
| `completed` | 已完成（已过开场时间） |

### 分账状态 (settlement status)

| 值 | 说明 |
|----|------|
| `pending` | 待分账（30天锁定期） |
| `processing` | 分账处理中 |
| `completed` | 分账完成 |
| `failed` | 分账失败 |

### 约球帖状态 (post status)

| 值 | 说明 |
|----|------|
| `open` | 招募中 |
| `closed` | 已关闭 |
| `full` | 已满员 |

### 报名审核状态 (registration status)

| 值 | 说明 |
|----|------|
| `pending` | 待审核 |
| `approved` | 已通过 |
| `rejected` | 已拒绝 |

### 比赛状态 (tournament status)

| 值 | 说明 |
|----|------|
| `draft` | 草稿 |
| `open` | 报名中 |
| `ongoing` | 进行中 |
| `finished` | 已结束 |
| `cancelled` | 已取消 |

### 运动类型 (sport_type)

| 值 | 说明 |
|----|------|
| `badminton` | 羽毛球 |
| `basketball` | 篮球 |
| `tennis` | 网球 |
| `table_tennis` | 乒乓球 |
| `football` | 足球 |
| `volleyball` | 排球 |
| `swimming` | 游泳 |
| `golf` | 高尔夫 |

> 运动类型为字符串存储，如需新增直接传新值即可，无需改表结构。
