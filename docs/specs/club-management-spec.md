# Club Management Module Spec (俱乐部管理)

## Overview
Club Management module allows club admins to view and manage their club's basic information. It serves as the admin dashboard entry point for club-related operations.

## Target User
Club admins (`club_admin` role) who own or manage at least one club.

## Pages

### 1. Club Dashboard (`pages/profile/club-dashboard`)

**Purpose:** Admin dashboard showing club overview and navigation to sub-modules.

**Layout:**
- Top: Club info card (cover image, name, address, phone, status badge)
- Middle: Quick stats row (venue count, today orders, today revenue)
- Bottom: Management menu grid (4 items in 2x2)
  - 场地管理 → `pages/publish/venue-manage?club_id={id}`
  - 时段管理 → `pages/publish/slot-manage?club_id={id}`
  - 订单管理 → `pages/publish/order-manage?club_id={id}`
  - 编辑信息 → `pages/publish/club-create?club_id={id}&mode=edit`

**Data Loading:**
```javascript
// Fetch club info + stats
GET /clubs/{club_id}          → ClubDetail
GET /clubs/{club_id}/stats    → ClubStats
```

**Permissions:**
- Guard: `requireClubAdmin()` in `onShow`
- If user manages multiple clubs, show a club selector at top

**Error States:**
- No managed clubs: show "您还没有管理的俱乐部" with "创建俱乐部" button
- Load failure: toast + back

---

### 2. Club Edit (`pages/publish/club-create` with `mode=edit`)

**Purpose:** Reuse existing `club-create` page with edit mode.

**Behavior when `mode=edit`:**
- Page title changes to "编辑俱乐部"
- Load existing club data via `GET /clubs/{club_id}`
- Pre-fill form fields
- Submit via `PUT /clubs/{club_id}` instead of `POST /clubs`
- Images: reuse existing upload flow via `app.uploadFile()`

**Form Fields:**
- 俱乐部名称 (name) - required, max 128 chars
- 运动类型 (sport_types) - multi-select: 羽毛球, 篮球, 网球, 乒乓球, 足球
- 俱乐部简介 (description) - optional textarea
- 封面图片 (cover_image) - single image upload
- 俱乐部相册 (images) - multiple image upload, max 9
- 详细地址 (address) - optional
- 联系电话 (contact_phone) - optional
- 坐标 (latitude, longitude) - optional, via map picker

**Navigation:**
- From club-dashboard: `wx.navigateTo({ url: '/pages/publish/club-create?club_id={id}&mode=edit' })`

---

## Backend APIs (existing, verify coverage)

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/clubs/{club_id}` | public | Get club detail |
| PUT | `/clubs/{club_id}` | club_admin | Update club info |
| GET | `/clubs/{club_id}/stats` | club_admin | Get club statistics |

**Verification:** All three endpoints already exist in `backend/app/api/v1/clubs.py`. No backend changes needed for this module.

---

## Data Flow

```
Profile Page → Club Dashboard
                  ├── GET /clubs/{id} → display club info
                  ├── GET /clubs/{id}/stats → display stats
                  ├── Tap "编辑信息" → Club Create (edit mode)
                  │     ├── GET /clubs/{id} → pre-fill form
                  │     └── PUT /clubs/{id} → save changes
                  ├── Tap "场地管理" → Venue Manage
                  ├── Tap "时段管理" → Slot Manage
                  └── Tap "订单管理" → Order Manage
```

---

## UI Specifications

### Club Info Card
- Full-width cover image, 300rpx height, `mode="aspectFill"`
- Club name: 36rpx, bold, white text with text-shadow over image
- Status badge: "营业中" (green) / "休息中" (gray)
- Address row: 📍 icon + address text, 28rpx gray
- Phone row: 📞 icon + phone number, tap to call

### Stats Row
- 3 columns, centered
- Numbers: 40rpx bold primary color
- Labels: 24rpx gray
- Stats: 场地数 | 今日订单 | 今日收入

### Menu Grid
- 2x2 grid, each cell 50% width
- Icon: 48rpx emoji + text label below
- Cell padding: 40rpx vertical
- Border: 1rpx solid #eee between cells
- Tap feedback: background #f5f5f5

---

## Edge Cases
1. User is admin of multiple clubs → show club picker dropdown
2. Club has no venues yet → stats show 0, menu still accessible
3. Network error on stats → show "--" for failed stat values
4. Phone missing → hide phone row entirely
