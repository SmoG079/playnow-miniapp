# Venue Management Module Spec (场地管理)

## Overview
Venue Management module allows club admins to create, edit, delete venues (courts/fields) within their club, and generate time slots for booking.

## Target User
Club admins (`club_admin` role).

## Pages

### 1. Venue List (`pages/publish/venue-manage`)

**Purpose:** List all venues for a club with CRUD operations.

**Layout:**
- Top: Page title "场地管理" + club name subtitle
- List: Card per venue
  - Left: venue name, sport_type tag, price_per_hour, status badge
  - Right: edit button, delete button
- Bottom: "+ 添加场地" floating button
- Empty state: "暂无场地，点击添加"

**Data Loading:**
```javascript
GET /clubs/{club_id}/venues    → list[VenueBrief]
```

**Actions:**
- Tap venue card → Edit venue (navigate to edit form)
- Tap delete → Confirm dialog → `DELETE` request
- Tap "+ 添加场地" → Create venue form

**Delete Behavior:**
- Confirm with `wx.showModal`
- Call `DELETE /venues/{venue_id}/with-club/{club_id}`
- On success: remove from list, show toast
- Note: backend soft-deletes (sets status=closed), not hard delete

---

### 2. Venue Form (Create/Edit)

**Purpose:** Create or edit a single venue.

**Implementation:** Inline form within venue-manage page using a modal/popup, OR separate page. For simplicity, use modal overlay on venue-manage page.

**Form Fields:**
- 场地名称 (name) - required, max 64 chars
- 运动类型 (sport_type) - single select (same as club sport_types)
- 每小时价格 (price_per_hour) - required, Decimal, min 0.01
- 容纳人数 (max_capacity) - number, default 4
- 排序 (sort_order) - number, default 0
- 状态 (status) - radio: active / maintenance / closed

**APIs:**
```javascript
// Create
POST /venues/with-club/{club_id}
Body: { name, sport_type, price_per_hour, max_capacity, sort_order }

// Update
PUT /venues/{venue_id}/with-club/{club_id}
Body: { name, sport_type, price_per_hour, max_capacity, sort_order, status }
```

---

### 3. Slot Generation (`pages/publish/slot-manage`)

**Purpose:** Generate time slots for venues across a date range.

**Layout:**
- Top: Venue selector (picker/dropdown)
- Date range: start date + end date pickers
- Time range: start time + end time pickers
- Interval: 30min / 60min / 90min radio group
- Generate button
- Results area: show count of created slots

**Data Loading:**
```javascript
GET /clubs/{club_id}/venues    → venue list for picker
```

**Generation API:**
```javascript
POST /venues/{venue_id}/slots/batch
Body: {
  date_from: "2026-06-15",
  date_to: "2026-06-21",
  start_time: "08:00",
  end_time: "22:00",
  interval_minutes: 60
}
```

**Validation:**
- `date_to` >= `date_from`
- `end_time` > `start_time`
- `interval_minutes` >= 30
- Max 31 days range (prevent abuse)

**Existing Slots Warning:**
- If slots already exist for some dates/times, backend skips them
- Show message: "已跳过 X 个已存在的时段，新增 Y 个时段"

---

## Backend APIs (existing, verify coverage)

| Method | Endpoint | Auth | Status |
|--------|----------|------|--------|
| GET | `/clubs/{club_id}/venues` | public | EXISTS |
| POST | `/venues/with-club/{club_id}` | club_admin | EXISTS |
| PUT | `/venues/{venue_id}/with-club/{club_id}` | club_admin | EXISTS |
| DELETE | `/venues/{venue_id}/with-club/{club_id}` | club_admin | EXISTS |
| POST | `/venues/{venue_id}/slots/batch` | club_admin | EXISTS |

**Verification:** All endpoints exist in `backend/app/api/v1/venues.py` and `clubs.py`. No backend changes needed.

---

## Data Flow

```
Club Dashboard → Venue Manage
  ├── GET /clubs/{id}/venues → render venue cards
  ├── Tap "+" → Show create modal
  │     └── POST /venues/with-club/{id} → refresh list
  ├── Tap "Edit" → Show edit modal
  │     └── PUT /venues/{vid}/with-club/{id} → refresh list
  ├── Tap "Delete" → Confirm → DELETE → refresh list
  └── Tap "时段管理" → Slot Manage
        ├── GET /clubs/{id}/venues → venue picker
        └── POST /venues/{vid}/slots/batch → show result
```

---

## UI Specifications

### Venue Card
- Background: white, border-radius 12rpx, margin 20rpx
- Padding: 24rpx
- Name: 32rpx bold
- Sport tag: 22rpx, bg #e8f5e9, text #2e7d32, padding 4rpx 12rpx, border-radius 8rpx
- Price: 28rpx, color #ff6b6b, "¥{price}/小时"
- Status badge:
  - active: 绿色 "正常"
  - maintenance: 橙色 "维护中"
  - closed: 灰色 "已关闭"
- Actions: two text buttons, "编辑" blue, "删除" red

### Create/Edit Modal
- Full-screen overlay, white background from bottom
- Form fields stacked vertically, 24rpx gap
- Input styling: border-bottom 1rpx #eee, height 80rpx
- Submit button: full-width green btn at bottom

### Slot Generation Page
- Form layout, padding 30rpx
- Venue picker: `picker` component
- Date pickers: `picker` mode="date"
- Time pickers: `picker` mode="time"
- Interval: radio buttons in row
- Generate button: green, full-width
- Result: green text showing created count

---

## Edge Cases
1. Venue name duplicate within club → backend returns 400, show error
2. Delete venue with existing bookings → backend soft-closes, bookings preserved
3. Generate slots for past dates → backend allows (admin override), show warning
4. All venues closed → show empty state with "添加场地" button
5. No venue selected for slot generation → disable generate button
