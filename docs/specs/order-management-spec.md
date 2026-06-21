# Order Management Module Spec (管理订单)

## Overview
Order Management module allows club admins to view and handle booking orders for their club. Includes order listing, filtering, detail view, and cancellation handling.

## Target User
Club admins (`club_admin` role).

## Pages

### 1. Order List (`pages/publish/order-manage`)

**Purpose:** List all booking orders for the admin's club with filtering and status badges.

**Layout:**
- Top: Status filter tabs (全部 | 待支付 | 已支付 | 已完成 | 已取消)
- List: Order cards
  - Top row: order_no, status badge, date
  - Middle: venue name, time slot, user nickname/phone
  - Bottom: amount ¥XXX, action buttons (cancel, view detail)
- Pull-to-refresh supported
- Infinite scroll (load more)
- Empty state: "暂无订单"

**Data Loading:**
```javascript
GET /bookings/club/{club_id}?status={status}&page={page}&page_size={page_size}
→ PaginatedResponse with BookingDetail items
```

**Status Tabs:**
- 全部 (all) → no status filter
- 待支付 (pending) → `status=pending`
- 已支付 (paid) → `status=paid`
- 已完成 (completed) → `status=completed`
- 已取消 (cancelled) → `status=cancelled`

**Status Badge Colors:**
- pending: orange #ff9800
- paid: green #4caf50
- completed: blue #2196f3
- cancelled: gray #9e9e9e
- refunding: red #f44336

**Actions per Order:**
- Tap card → show order detail modal
- Cancel button (only for pending/paid): `POST /bookings/{id}/cancel`

---

### 2. Order Detail Modal

**Purpose:** Full order information display.

**Layout (modal/popup):**
- Order number: large text, copyable
- Status badge + order time
- Divider
- Venue info: name, address
- Time slot: date + start_time ~ end_time
- User info: nickname, phone (if available)
- Amount: ¥XXX large text
- Payment info: payment_time, wx_transaction_id (if paid)
- Cancel reason (if cancelled)

**Data:** Already loaded from list API, no additional fetch needed.

---

## Backend APIs (existing, verify coverage)

| Method | Endpoint | Auth | Status |
|--------|----------|------|--------|
| GET | `/bookings/club/{club_id}` | club_admin | EXISTS |
| POST | `/bookings/{booking_id}/cancel` | owner | EXISTS |

**Verification:**
- `GET /bookings/club/{club_id}` exists in `bookings.py:275`. Returns `PaginatedResponse` with `BookingDetail` items.
- `POST /bookings/{booking_id}/cancel` exists in `bookings.py:223`. Requires the booking owner, NOT club admin.

**Issue Identified:** The cancel endpoint checks `order.user_id != current_user.id` and returns 403 if the caller is not the booking owner. A club admin cannot cancel a customer's booking on their behalf.

**Fix Required:** Update cancel endpoint to also allow club admins to cancel orders for their club.

```python
# In backend/app/api/v1/bookings.py cancel_booking:
# Change:
if order.user_id != current_user.id:
    raise HTTPException(status_code=403, detail="Not your booking")
# To:
if order.user_id != current_user.id:
    # Allow club admin to cancel orders for their club
    if _v(current_user.role) not in ("club_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Not your booking")
    # For club_admin, verify they manage this club
    if _v(current_user.role) == "club_admin":
        from app.models.models import ClubMember
        member = await db.execute(
            select(ClubMember).where(
                ClubMember.club_id == order.club_id,
                ClubMember.user_id == current_user.id,
            )
        )
        if not member.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not your booking")
```

---

## Data Flow

```
Club Dashboard → Order Manage
  ├── GET /bookings/club/{id}?status=&page=1 → render order cards
  ├── Tap status tab → reload with filter
  ├── Pull down → refresh current page
  ├── Scroll down → load next page
  ├── Tap order → show detail modal
  └── Tap "取消订单" (admin) → Confirm → POST /bookings/{id}/cancel → refresh
```

---

## UI Specifications

### Order Card
- Background: white, border-radius 12rpx, margin 20rpx, padding 24rpx
- Top row (flex, space-between):
  - Order no: 24rpx, color #666, mono font feel
  - Status badge: 22rpx, padding 4rpx 16rpx, border-radius 8rpx
- Date: 24rpx, color #999, right-aligned
- Venue row: 🏟️ + venue name, 28rpx, margin-top 16rpx
- Time row: 🕐 + "YYYY-MM-DD HH:MM ~ HH:MM", 26rpx, color #666
- User row: 👤 + nickname, 26rpx, color #666
- Bottom row (flex, space-between, align-end):
  - Amount: "¥" + price, 32rpx, bold, color #ff6b6b
  - Actions: "查看" button (outline), "取消" button (red, only for pending/paid)

### Filter Tabs
- Horizontal scroll, sticky top
- Each tab: padding 20rpx 30rpx, font 28rpx
- Active: bold, color #333, bottom border 4rpx #4CD964
- Inactive: color #999

### Order Detail Modal
- Mask: rgba(0,0,0,0.5)
- Content: white card, border-radius 24rpx 24rpx 0 0, from bottom
- Padding: 40rpx
- Max height: 80vh, scrollable
- Close: X button top-right, or tap mask
- Sections separated by 1rpx #eee dividers

---

## Edge Cases
1. Order list empty → show empty state illustration + "暂无订单"
2. Pagination end → disable pull-up, show "没有更多了"
3. Cancel paid order → show refund amount calculation, confirm modal
4. Cancel already cancelled order → button hidden, no action
5. Network error on list → show error state, tap to retry
6. Admin not authorized for this club → 403, navigate back
