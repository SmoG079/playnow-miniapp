# Settlement (Profit-Sharing) Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Implement the missing WeChat Pay V3 profit-sharing execution for paid booking orders, triggered by a periodic Celery task after a configurable delay.

**Architecture:** A `SettlementRecord` created during the payment callback will carry a `scheduled_at` timestamp. A Celery beat task polls for due pending records, calls `wechatpayv3.profitsharing_order`, and updates status via the query API. Platform admins can query/refresh status through a new admin endpoint.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Celery, wechatpayv3, MySQL, Redis.

---

## File Structure

- `backend/app/models/models.py` — add `scheduled_at`, `retry_count`, `out_order_no` to `SettlementRecord`.
- `backend/app/core/config.py` — add settlement tuning settings.
- `backend/app/services/settlement.py` — new service module: `execute_settlement`, `query_settlement_status`.
- `backend/app/tasks/tasks.py` — new Celery task `execute_pending_settlements`.
- `backend/app/tasks/worker.py` — register beat schedule.
- `backend/app/api/v1/bookings.py` — update `_handle_payment_success` to schedule record; add admin endpoints.
- `backend/app/schemas/schemas.py` — add settlement request/response schemas.
- `docs/module-b-fix-progress.md` — mark P0-6 complete.

---

## Task 1: Extend SettlementRecord model

**Files:**
- Modify: `backend/app/models/models.py:202-218`

- [ ] **Step 1: Add new columns to `SettlementRecord`**

```python
class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"), nullable=False)
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    platform_amount = Column(DECIMAL(10, 2), nullable=False)
    club_amount = Column(DECIMAL(10, 2), nullable=False)
    split_ratio = Column(DECIMAL(4, 3), nullable=False)
    wx_split_order_no = Column(String(64))          # WeChat profit-sharing order id
    out_order_no = Column(String(64), unique=True)  # merchant profit-sharing order no
    status = Column(Enum(SettlementStatus), default=SettlementStatus.pending, nullable=False)
    fail_reason = Column(String(512))
    retry_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=False) # when settlement may execute
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    order = relationship("BookingOrder", back_populates="settlement")
```

- [ ] **Step 2: Add a unique index on `out_order_no`**

`unique=True` on the column is sufficient.

---

## Task 2: Add settlement configuration

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add settings after the `FREE_CANCEL_HOURS` line**

```python
    # Settlement / profit-sharing
    SETTLEMENT_DELAY_DAYS: int = 30
    SETTLEMENT_MAX_RETRIES: int = 3
    SETTLEMENT_PLATFORM_ACCOUNT: str = ""  # platform mch_id or openid
```

Note: `SETTLEMENT_PLATFORM_ACCOUNT` is the receiver account for the platform portion if we choose to include it in receivers. For the simplest initial implementation, only the club is included as a receiver and `unfreeze_unsplit=True` sends the platform portion to the platform merchant automatically.

---

## Task 3: Create settlement execution service

**Files:**
- Create: `backend/app/services/settlement.py`

- [ ] **Step 1: Write the service file**

```python
import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.wechat_pay import get_wxpay
from app.models.models import SettlementRecord, SettlementStatus, BookingOrder, OrderStatus, Club

logger = logging.getLogger(__name__)


def _to_cents(amount: Decimal) -> int:
    return int((amount * Decimal("100")).quantize(Decimal("1")))


async def execute_settlement(session: AsyncSession, settlement_id: int) -> SettlementRecord:
    """Call WeChat profit-sharing API for a pending settlement record."""
    settings = get_settings()
    wxpay = get_wxpay()

    result = await session.execute(
        select(SettlementRecord, BookingOrder, Club)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .join(Club, SettlementRecord.club_id == Club.id)
        .where(SettlementRecord.id == settlement_id)
    )
    row = result.first()
    if not row:
        raise ValueError(f"Settlement {settlement_id} not found")

    settlement, order, club = row

    if settlement.status not in (SettlementStatus.pending, SettlementStatus.failed):
        logger.info("Settlement %s already executed (status=%s)", settlement.id, settlement.status)
        return settlement

    if order.status != OrderStatus.paid:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = f"Order status is {order.status}, expected paid"
        await session.commit()
        return settlement

    if not order.wx_transaction_id:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "Missing wx_transaction_id"
        await session.commit()
        return settlement

    if not club.sub_merchant_id:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "Club missing sub_merchant_id"
        await session.commit()
        return settlement

    if not settlement.out_order_no:
        settlement.out_order_no = f"PS{order.order_no}"

    club_amount_cents = _to_cents(settlement.club_amount)

    try:
        resp = wxpay.profitsharing_order(
            transaction_id=order.wx_transaction_id,
            out_order_no=settlement.out_order_no,
            receivers=[
                {
                    "type": "MERCHANT_ID",
                    "account": club.sub_merchant_id,
                    "amount": club_amount_cents,
                    "currency": "CNY",
                    "description": "场地预约分账",
                }
            ],
            unfreeze_unsplit=True,
        )
        settlement.wx_split_order_no = resp.get("order_id")
        settlement.status = SettlementStatus.processing
        settlement.retry_count = 0
        settlement.fail_reason = None
        logger.info("Profit-sharing order created: %s", settlement.wx_split_order_no)
    except Exception as exc:
        settlement.retry_count += 1
        if settlement.retry_count >= settings.SETTLEMENT_MAX_RETRIES:
            settlement.status = SettlementStatus.failed
        settlement.fail_reason = str(exc)[:500]
        logger.exception("Profit-sharing order failed for settlement %s", settlement.id)

    await session.commit()
    return settlement


async def query_settlement_status(session: AsyncSession, settlement_id: int) -> SettlementRecord:
    """Query WeChat for current profit-sharing status and update the record."""
    wxpay = get_wxpay()

    result = await session.execute(
        select(SettlementRecord, BookingOrder)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .where(SettlementRecord.id == settlement_id)
    )
    row = result.first()
    if not row:
        raise ValueError(f"Settlement {settlement_id} not found")

    settlement, order = row

    if not settlement.out_order_no or not order.wx_transaction_id:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "Missing out_order_no or transaction_id"
        await session.commit()
        return settlement

    try:
        resp = wxpay.profitsharing_order_query(
            transaction_id=order.wx_transaction_id,
            out_order_no=settlement.out_order_no,
        )
        state = resp.get("state")
        receivers = resp.get("receivers", [])

        if state == "FINISHED" and all(r.get("result") == "SUCCESS" for r in receivers):
            settlement.status = SettlementStatus.completed
            settlement.completed_at = datetime.utcnow()
            settlement.fail_reason = None
        elif state == "PROCESSING":
            settlement.status = SettlementStatus.processing
        else:
            settlement.status = SettlementStatus.failed
            settlement.fail_reason = f"state={state}, receivers={receivers}"

        await session.commit()
    except Exception as exc:
        logger.exception("Settlement status query failed for %s", settlement.id)
        settlement.fail_reason = f"query error: {exc}"[:500]
        await session.commit()

    return settlement
```

---

## Task 4: Update payment callback to schedule settlement

**Files:**
- Modify: `backend/app/api/v1/bookings.py` (inside `_handle_payment_success`)

- [ ] **Step 1: Locate the SettlementRecord creation block and update it**

The existing code looks approximately like:

```python
# Create settlement record
settlement = SettlementRecord(
    order_id=order.id,
    total_amount=order.amount,
    platform_amount=platform_amount,
    club_amount=club_amount,
    split_ratio=club.split_ratio or Decimal("0.1"),
)
```

Replace it with:

```python
from datetime import timedelta  # add at top of file if not present

# Create settlement record
settings = get_settings()
settlement = SettlementRecord(
    order_id=order.id,
    total_amount=order.amount,
    platform_amount=platform_amount,
    club_amount=club_amount,
    split_ratio=club.split_ratio or Decimal("0.1"),
    out_order_no=f"PS{order.order_no}",
    scheduled_at=(payment_time or datetime.utcnow()) + timedelta(days=settings.SETTLEMENT_DELAY_DAYS),
)
```

Ensure `payment_time` is captured before this block from the WeChat callback data (e.g., `success_time`).

---

## Task 5: Add Celery settlement task and beat schedule

**Files:**
- Modify: `backend/app/tasks/tasks.py`
- Modify: `backend/app/tasks/worker.py`

- [ ] **Step 1: Add task in `tasks.py`**

```python
@celery_app.task(name="app.tasks.tasks.execute_pending_settlements")
def execute_pending_settlements():
    """Poll for due pending settlements and execute profit-sharing."""
    import asyncio
    from sqlalchemy import select
    from app.core.database import async_session_factory
    from app.services.settlement import execute_settlement, query_settlement_status
    from app.models.models import SettlementRecord, SettlementStatus

    async def _run():
        async with async_session_factory() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(SettlementRecord.id)
                .where(
                    SettlementRecord.status.in_([SettlementStatus.pending, SettlementStatus.failed]),
                    SettlementRecord.scheduled_at <= now,
                    SettlementRecord.retry_count < 3,
                )
                .order_by(SettlementRecord.scheduled_at)
            )
            ids = [r[0] for r in result.all()]

            for sid in ids:
                rec = await execute_settlement(session, sid)
                if rec.status == SettlementStatus.processing and rec.wx_split_order_no:
                    await query_settlement_status(session, sid)

    return asyncio.run(_run())
```

- [ ] **Step 2: Register beat schedule in `worker.py`**

Add to `beat_schedule`:

```python
    "execute-pending-settlements": {
        "task": "app.tasks.tasks.execute_pending_settlements",
        "schedule": crontab(hour="3", minute="0"),
    },
```

---

## Task 6: Add admin settlement endpoints

**Files:**
- Modify: `backend/app/api/v1/bookings.py`
- Modify: `backend/app/schemas/schemas.py`

- [ ] **Step 1: Add schemas**

In `backend/app/schemas/schemas.py`:

```python
class SettlementDetail(BaseModel):
    id: int
    order_id: int
    order_no: str
    total_amount: Decimal
    platform_amount: Decimal
    club_amount: Decimal
    split_ratio: Decimal
    status: str
    wx_split_order_no: Optional[str]
    out_order_no: Optional[str]
    retry_count: int
    scheduled_at: Optional[datetime]
    completed_at: Optional[datetime]
    fail_reason: Optional[str]

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Add admin endpoints in `bookings.py`**

```python
from app.services.settlement import execute_settlement, query_settlement_status


@router.get("/settlements", response_model=List[SettlementDetail])
async def list_settlements(
    status: Optional[str] = None,
    club_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    from sqlalchemy import select
    from app.models.models import SettlementRecord, BookingOrder

    stmt = (
        select(SettlementRecord, BookingOrder.order_no)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .order_by(SettlementRecord.created_at.desc())
    )
    if status:
        stmt = stmt.where(SettlementRecord.status == status)
    if club_id:
        stmt = stmt.where(SettlementRecord.club_id == club_id)

    result = await db.execute(stmt)
    rows = result.all()
    out = []
    for rec, order_no in rows:
        detail = SettlementDetail.from_orm(rec)
        detail.order_no = order_no
        out.append(detail)
    return out


@router.post("/settlements/{settlement_id}/query", response_model=SettlementDetail)
async def query_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    rec = await query_settlement_status(db, settlement_id)
    return SettlementDetail.from_orm(rec)


@router.post("/settlements/{settlement_id}/retry", response_model=SettlementDetail)
async def retry_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    rec = await db.get(SettlementRecord, settlement_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if rec.status == SettlementStatus.completed:
        raise HTTPException(status_code=400, detail="Settlement already completed")
    rec.status = SettlementStatus.pending
    rec.retry_count = 0
    await db.commit()
    rec = await execute_settlement(db, settlement_id)
    if rec.status == SettlementStatus.processing:
        rec = await query_settlement_status(db, settlement_id)
    return SettlementDetail.from_orm(rec)
```

---

## Task 7: Update fix-progress documentation

**Files:**
- Modify: `docs/module-b-fix-progress.md`

- [ ] **Step 1: Mark P0-6 as completed**

In the P0 table, set `P0-6 | 结算（分账）执行完全缺失 | ✅ | Claude | 新增 SettlementRecord 字段、Celery 调度任务、微信分账 API 调用、管理员查询/重试接口`.

---

## Verification

- Run `python -m py_compile backend/app/services/settlement.py backend/app/tasks/tasks.py backend/app/api/v1/bookings.py backend/app/models/models.py`.
- Start the API and verify it boots without import errors.
- Use WeChat Pay sandbox (if available) to simulate a profit-sharing order.
- Verify Celery beat schedule is registered via `celery -A app.tasks.worker beat -l info`.
