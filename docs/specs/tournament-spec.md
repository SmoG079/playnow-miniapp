# Tournament System Spec

## Overview
Complete the tournament feature so club admins can create tournaments and users can register (and pay if there is an entry fee). This spec covers the tournament detail page, tournament creation page, and the backend registration + payment flow.

## Target Users
- **Tournament creators:** club admins (`club_admin` / `platform_admin`)
- **Registrants:** any logged-in user

---

## 1. Tournament Detail Page (`pages/common/tournament-detail`)

**Purpose:** Display tournament information and let users register.

### Layout
- Cover image header with back button
- Title + sport type badge
- Info section:
  - Club name
  - Start / end time
  - Entry fee
  - Max participants / current participants
  - Prize (if provided)
- Description section
- Bracket section (placeholder)
- Bottom action bar:
  - Share button
  - Register button (state-aware)

### Data Loading
```javascript
GET /tournaments/{id}
→ TournamentDetail
```

### Registration Button States
| State | Button Text | Action |
|-------|-------------|--------|
| Not logged in | "登录后报名" | navigate to login |
| Tournament not open | "报名未开始" | disabled |
| Full | "已满员" | disabled |
| Already registered + fee unpaid | "去支付" | POST /tournaments/{id}/pay → wx.requestPayment |
| Already registered + paid/confirmed | "已报名" | disabled |
| Free tournament, not registered | "立即报名" | POST /tournaments/{id}/register |
| Paid tournament, not registered | "报名 ¥{fee}" | POST /tournaments/{id}/register → if fee > 0 then POST /tournaments/{id}/pay |

### Share
- `onShareAppMessage` returns title + path `/pages/common/tournament-detail?id={id}`

### Bracket Placeholder
- Section title "赛程安排"
- Centered text "赛程将在报名截止后生成"

---

## 2. Tournament Create Page (`pages/publish/tournament-create`)

**Purpose:** Club admin creates a new tournament.

### Access Control
- Guard with `requireClubAdmin()`
- Redirect to login or back if not a club admin

### Form Fields
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| Tournament name | input | yes | |
| Club | picker | yes | from managed clubs; auto-select if only one |
| Sport type | input/picker | yes | default "网球" |
| Start time | picker (datetime) | yes | |
| End time | picker (datetime) | yes | must be after start |
| Registration fee | input (number) | yes | default 0 (free) |
| Max participants | input (number) | no | |
| Description | textarea | no | |
| Prize | textarea | no | |

### Submission
```javascript
POST /tournaments
{
  club_id,
  title,
  sport_type,
  start_time,   // ISO 8601 string from picker
  end_time,
  entry_fee,
  max_participants,
  description,
  prize
}
→ TournamentBrief
```

### Behavior
- Validate required fields
- Validate end > start
- On success, show toast and navigate to detail page: `/pages/common/tournament-detail?id={id}`

---

## 3. Backend: Tournament Registration Payment Flow

### Current State
`backend/app/api/v1/tournaments.py` has:
- CRUD endpoints
- `POST /tournaments/{id}/register` creates a `TournamentRegistration` but has a TODO for payment at line 220
- No `/tournaments/{id}/pay` endpoint

### Required Changes

#### 3.1 Model Update
Tournament registrations are currently stored in `tournament_registrations` table. We need to link them to a `BookingOrder` when there is a fee. The model already has `order_id` on `TournamentRegistration`.

#### 3.2 New Schema Fields
Add `prize` field support in `TournamentCreate` / `TournamentUpdate` / `TournamentDetail` schemas.

#### 3.3 POST /tournaments/{id}/register
**Behavior:**
1. Load tournament. Return 404 if not found.
2. Validate tournament status is `open`.
3. Validate not full.
4. Validate user has not already registered.
5. Create `TournamentRegistration` with status `registered`.
6. If `entry_fee > 0`:
   - Create a `BookingOrder` with:
     - `order_no` generated
     - `user_id = current_user.id`
     - `venue_id = tournament.venue_id` (can be null)
     - `slot_id = None` (tournament does not use venue slots)
     - `club_id = tournament.club_id`
     - `amount = entry_fee`
     - `status = pending`
   - Link `TournamentRegistration.order_id = order.id`
   - Set `TournamentRegistration.status = registered` (unpaid)
7. If `entry_fee == 0`:
   - Increment `tournament.current_participants`
   - Set `TournamentRegistration.status = confirmed`

**Response:**
```json
{
  "msg": "ok",
  "registration_id": 123,
  "order": { ...BookingDetail... } | null
}
```

#### 3.4 POST /tournaments/{id}/pay
**Behavior:**
1. Load tournament and current user's registration.
2. If no registration or already paid/confirmed, return error.
3. Get pending `BookingOrder` from `registration.order_id`.
4. Call WeChat Pay V3 to create a JSAPI payment order:
   - `out_trade_no = order.order_no`
   - `amount.total = int(entry_fee * 100)`
   - `description = tournament.title`
   - `payer.openid` from user's `openid`
5. Return payment params for `wx.requestPayment`:
```json
{
  "timeStamp": "...",
  "nonceStr": "...",
  "package": "prepay_id=...",
  "signType": "RSA",
  "paySign": "..."
}
```

#### 3.5 Payment Callback Reuse
Tournament registration orders will be paid through the same `POST /bookings/wx-notify` callback (which now verifies signatures). To differentiate tournament registrations, we can check if the `out_trade_no` belongs to a `BookingOrder` whose `venue_id` is null / linked to a `TournamentRegistration`. For MVP, reuse the same callback and on payment success:
- Update `BookingOrder.status = paid`
- Find linked `TournamentRegistration` by `order_id`
- Set `status = confirmed`
- Increment `tournament.current_participants`
- Send notification

This callback logic currently lives in `bookings.py`. We should either:
- Extract a shared payment completion service, OR
- Keep it simple and add tournament handling inside `bookings.py` wx_pay_notify

**Decision:** Keep it simple. After updating order to paid in `bookings.py`, check if a `TournamentRegistration` references this order. If yes, update registration status and participant count.

### WeChat Pay Helper Extension
`miniprogram/utils/wxpay.js` currently only has `payBooking`. Add a generic `payOrder(orderId)` that calls `/bookings/{orderId}/pay` (reused for tournament orders). Then `payBooking` can delegate to `payOrder`.

---

## Data Flow

### Create Tournament
```
Club Dashboard / Profile
  → /pages/publish/tournament-create
    → POST /tournaments
      → redirect to /pages/common/tournament-detail?id={id}
```

### Register for Tournament
```
Tournament Detail
  → POST /tournaments/{id}/register
    → entry_fee == 0: confirmed
    → entry_fee > 0:
      → create BookingOrder (pending)
      → POST /tournaments/{id}/pay
        → wx.requestPayment
        → WeChat callback → POST /bookings/wx-notify
          → order.status = paid
          → registration.status = confirmed
          → current_participants += 1
          → notification
```

---

## API Reference

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/tournaments/{id}` | any | Tournament detail |
| POST | `/tournaments` | club_admin | Create tournament |
| POST | `/tournaments/{id}/register` | current_user | Register |
| POST | `/tournaments/{id}/pay` | current_user | Get payment params |
| POST | `/bookings/{id}/pay` | current_user | **REUSED** for any pending order |
| POST | `/bookings/wx-notify` | WeChat | Payment callback |

---

## Files to Modify / Create

| Path | Action | Description |
|------|--------|-------------|
| `docs/specs/tournament-spec.md` | Create | This spec |
| `backend/app/schemas/schemas.py` | Modify | Add `prize` field to tournament schemas |
| `backend/app/api/v1/tournaments.py` | Modify | Implement register + pay endpoints |
| `backend/app/api/v1/bookings.py` | Modify | Handle tournament registration in wx_pay_notify |
| `miniprogram/utils/wxpay.js` | Modify | Add `payOrder` helper |
| `miniprogram/pages/common/tournament-detail.js` | Rewrite | Detail page logic |
| `miniprogram/pages/common/tournament-detail.wxml` | Rewrite | Detail page layout |
| `miniprogram/pages/common/tournament-detail.wxss` | Rewrite | Detail page styles |
| `miniprogram/pages/common/tournament-detail.json` | Modify | Page config |
| `miniprogram/pages/publish/tournament-create.js` | Rewrite | Create form logic |
| `miniprogram/pages/publish/tournament-create.wxml` | Rewrite | Create form layout |
| `miniprogram/pages/publish/tournament-create.wxss` | Rewrite | Create form styles |
| `miniprogram/pages/publish/tournament-create.json` | Modify | Page config |

---

## Edge Cases
1. Non-admin tries to create tournament → `requireClubAdmin()` blocks
2. User not logged in on detail → redirect to login on register tap
3. Tournament full → disable register button
4. Already registered → show correct status
5. Paid registration cancelled by user → registration remains `registered`, order `pending`; can re-pay
6. WeChat Pay callback for tournament order → update registration status
7. Free tournament → no order created, status immediately `confirmed`
