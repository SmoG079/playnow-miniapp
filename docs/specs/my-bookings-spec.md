# My Bookings Module Spec (我的预约)

## Overview
My Bookings page allows logged-in users to view their own venue booking orders, filter by status, and cancel pending orders.

## Target User
All logged-in users (`user`, `club_admin`, `platform_admin` roles).

## Pages

### 1. My Bookings List (`pages/profile/my-bookings`)

**Purpose:** List the current user's booking orders with status filtering and order cards.

**Layout:**
- Top: Status filter tabs (全部 | 待支付 | 已支付 | 已完成 | 已取消)
- List: Booking cards
  - Top row: order_no, status badge
  - Middle: club name, venue name, time slot
  - Bottom: amount ¥XXX, action button (cancel for pending)
- Pull-to-refresh supported
- Infinite scroll (load more)
- Empty state: "暂无预约"

**Data Loading:**
```javascript
GET /users/me/bookings?status={status}&page={page}&page_size={page_size}
→ PaginatedResponse with BookingDetail items
```

**Status Tabs:**
- 全部 (all) → no status filter
- 待支付 (pending) → `status=pending`
- 已支付 (paid) → `status=paid`
- 已完成 (completed) → `status=completed`
- 已取消 (cancelled) → `status` in (`cancelled`, `refunding`, `refunded`)

**Status Badge Colors:**
- pending: orange #ff9800
- paid: green #4caf50
- completed: blue #2196f3
- cancelled: gray #9e9e9e
- refunding: red #f44336
- refunded: gray #9e9e9e

**Actions per Order:**
- Cancel button (only for pending): `POST /bookings/{id}/cancel`
- Paid orders cannot be cancelled from this page (backend may allow with refund logic; keep simple for MVP)

---

## Backend APIs

| Method | Endpoint | Auth | Status |
|--------|----------|------|--------|
| GET | `/users/me/bookings` | current_user | **TO IMPLEMENT** |
| POST | `/bookings/{booking_id}/cancel` | booking owner | EXISTS |

### New Endpoint: GET /users/me/bookings

**Location:** `backend/app/api/v1/users.py`

**Behavior:**
- Return paginated list of `BookingOrder` records where `user_id == current_user.id`
- Optional `status` query parameter
- When `status == 'cancelled'`, return orders whose status is in `('cancelled', 'refunding', 'refunded')`
- Join `Venue`, `Club`, `VenueTimeSlot` to populate `BookingDetail` fields
- Sort by `created_at DESC`

**Response:** `PaginatedResponse` with `BookingDetail` items.

```python
@router.get("/me/bookings", response_model=PaginatedResponse)
async def my_bookings(
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(BookingOrder, Venue.name, Club.name, VenueTimeSlot.date, VenueTimeSlot.start_time, VenueTimeSlot.end_time) \
        .join(Venue, BookingOrder.venue_id == Venue.id) \
        .join(Club, BookingOrder.club_id == Club.id) \
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id) \
        .where(BookingOrder.user_id == current_user.id)

    count_query = select(func.count(BookingOrder.id)).where(BookingOrder.user_id == current_user.id)

    if status == "cancelled":
        query = query.where(BookingOrder.status.in_((OrderStatus.cancelled, OrderStatus.refunding, OrderStatus.refunded)))
        count_query = count_query.where(BookingOrder.status.in_((OrderStatus.cancelled, OrderStatus.refunding, OrderStatus.refunded)))
    elif status:
        query = query.where(BookingOrder.status == status)
        count_query = count_query.where(BookingOrder.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(BookingOrder.created_at.desc()).offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for row in rows:
        order, venue_name, club_name, slot_date, slot_start, slot_end = row
        items.append(BookingDetail(
            id=order.id, order_no=order.order_no, user_id=order.user_id,
            venue_id=order.venue_id, slot_id=order.slot_id, club_id=order.club_id,
            amount=order.amount, status=_v(order.status), payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=club_name, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
```

**Imports to add in `users.py`:**
```python
from sqlalchemy import select, func
from app.api.deps import _v
from app.models.models import BookingOrder, Venue, Club, VenueTimeSlot, OrderStatus
from app.schemas.schemas import BookingDetail
```

---

## Data Flow

```
Profile Page → My Bookings
  ├── GET /users/me/bookings?status=&page=1 → render booking cards
  ├── Tap status tab → reload with filter
  ├── Pull down → refresh current tab
  ├── Scroll down → load next page
  └── Tap "取消" (pending only) → Confirm → POST /bookings/{id}/cancel → refresh
```

---

## UI Specifications

### Booking Card
- Background: white, border-radius 16rpx, margin 20rpx, padding 24rpx
- Top row (flex, space-between):
  - Order no: 24rpx, color #999, mono font feel
  - Status badge: 22rpx, padding 4rpx 16rpx, border-radius 8rpx
- Body:
  - Club row: 🏠 + club_name, 28rpx, color #333
  - Venue row: 🏟️ + venue_name, 26rpx, color #666
  - Time row: 🕐 + "YYYY-MM-DD HH:MM ~ HH:MM", 26rpx, color #666
- Bottom row (flex, space-between, align-center):
  - Amount: "¥" + price, 32rpx, bold, color #ff6b6b
  - Actions: "取消" button (red outline, only for pending)

### Filter Tabs
- Horizontal scroll, sticky top, white background, bottom border 1rpx #eee
- Each tab: padding 20rpx 30rpx, font 28rpx
- Active: bold, color #333, bottom border 4rpx #4CD964
- Inactive: color #999

### Empty / Loading States
- Empty: centered text "暂无预约", color #999, padding 120rpx
- Loading first page: centered text "加载中..."
- Load more: footer text "没有更多了" when `hasMore == false`

---

## Edge Cases
1. User not logged in → redirect to `/pages/common/login` via `requireLogin()` guard
2. Booking list empty → show empty state
3. Pagination end → disable further load, show "没有更多了"
4. Cancel pending order → confirm modal → POST cancel → refresh list
5. Cancel non-pending order → button hidden
6. Network error on list → show toast "加载失败", keep previous data if any
7. Tab switch while loading → ignore stale response

---

## Files to Modify / Create

| Path | Action | Description |
|------|--------|-------------|
| `docs/specs/my-bookings-spec.md` | Create | This spec |
| `backend/app/api/v1/users.py` | Modify | Add `GET /me/bookings` endpoint |
| `miniprogram/pages/profile/my-bookings.js` | Rewrite | Page logic, data loading, cancel |
| `miniprogram/pages/profile/my-bookings.wxml` | Rewrite | Tabs, card list, empty/loading states |
| `miniprogram/pages/profile/my-bookings.wxss` | Rewrite | Card, tabs, status colors |
| `miniprogram/pages/profile/my-bookings.json` | Modify | Enable pull-down refresh |
