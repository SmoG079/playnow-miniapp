# Refund Retry Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add an automatic retry mechanism for WeChat Pay V3 refund requests that fail transiently, using Celery and idempotent `out_refund_no` reuse.

**Architecture:** Create `RefundRecord` with `out_refund_no` **before** calling the WeChat refund API. On retryable failure, mark the record as `failed` and schedule a Celery retry task that queries refund status first, then resubmits with the same `out_refund_no`. Non-retryable failures are terminal.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Celery, wechatpayv3.

---

## File Structure

- `backend/app/models/models.py` — add `retry_count`, `scheduled_at`, `fail_reason` to `RefundRecord`.
- `backend/app/core/config.py` — add refund retry settings.
- `backend/app/api/v1/bookings.py` — restructure cancel/refund endpoints to create record before API call and handle retryable failures.
- `backend/app/tasks/tasks.py` — add `retry_failed_refunds` Celery task and `poll_processing_refunds` task.
- `backend/app/tasks/worker.py` — register beat schedules.
- `docs/module-b-fix-progress.md` — mark P1-8 complete.

---

## Task 1: Extend RefundRecord model

**Files:**
- Modify: `backend/app/models/models.py:387-404`

- [ ] **Step 1: Add new columns**

```python
class RefundRecord(Base):
    __tablename__ = "refund_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"), nullable=False)
    out_refund_no = Column(String(32), nullable=False, unique=True)
    wx_refund_id = Column(String(64))
    amount = Column(DECIMAL(10, 2), nullable=False)
    reason = Column(String(256))
    status = Column(String(32), default="pending")
    retry_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    fail_reason = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    __table_args__ = (
        Index("idx_refund_order", "order_id"),
        Index("idx_refund_status_scheduled", "status", "scheduled_at"),
    )

    order = relationship("BookingOrder", back_populates="refund_records")
```

---

## Task 2: Add refund retry configuration

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add settings after settlement settings**

```python
    # Refund retry
    REFUND_MAX_RETRIES: int = 5
    REFUND_RETRY_BACKOFF_BASE_SECONDS: int = 30
    REFUND_POLL_INTERVAL_MINUTES: int = 5
    REFUND_BATCH_SIZE: int = 50
```

---

## Task 3: Restructure refund initiation endpoints

**Files:**
- Modify: `backend/app/api/v1/bookings.py`

### Cancel endpoint (`POST /{booking_id}/cancel`)

Current code (lines 653-690) calls `wxpay.refund()` before creating `RefundRecord`. Restructure to:

1. Generate `out_refund_no`.
2. Create `RefundRecord(order_id=order.id, out_refund_no=out_refund_no, amount=refund_amount, reason=..., status="pending")` and add to session.
3. Try `wxpay.refund(...)`.
4. On success: set order status to `refunding`, order refund fields, commit.
5. On retryable exception (`SYSTEM_ERROR`, `BIZERR_NEED_RETRY`, network timeout, connection error): set record `status="failed"`, `retry_count=0`, `scheduled_at=now + backoff(0)`, `fail_reason`; enqueue Celery `retry_failed_refund` task; return `{"msg": "Refund queued for retry", "status": "refunding", "out_refund_no": out_refund_no}`.
6. On non-retryable exception: set record `status="failed"`, `fail_reason`; raise HTTPException(502/500).

### Admin refund endpoint (`POST /{booking_id}/refund`)

Same restructuring as cancel endpoint (current code lines 760-796).

- [ ] **Step 1: Extract a shared helper**

Add near the top of `bookings.py`:

```python
import httpx
from sqlalchemy.exc import IntegrityError

REFUND_RETRYABLE_CODES = {"SYSTEM_ERROR", "BIZERR_NEED_RETRY"}


def _is_refund_retryable(exc: Exception) -> bool:
    """Return True if a refund exception should be retried."""
    msg = str(exc).upper()
    if any(code in msg for code in REFUND_RETRYABLE_CODES):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    return False


def _refund_backoff_seconds(attempt: int) -> int:
    """Return retry delay for attempt index (0-based)."""
    settings = get_settings()
    base = settings.REFUND_RETRY_BACKOFF_BASE_SECONDS
    return min(base * (2 ** attempt), 1800)  # cap at 30 minutes
```

- [ ] **Step 2: Update cancel_booking refund block**

Replace the refund block (lines 653-690) with:

```python
    # If paid, trigger WeChat refund first; only release slot once WeChat confirms SUCCESS callback
    if _v(order.status) == "paid" and refund_amount > 0:
        if not order.wx_transaction_id:
            raise HTTPException(status_code=400, detail="Missing WeChat transaction id")

        wxpay = get_wxpay()
        out_refund_no = _generate_order_no()

        refund_record = RefundRecord(
            order_id=order.id,
            out_refund_no=out_refund_no,
            amount=refund_amount,
            reason=req.reason or "用户取消订单",
            status="pending",
        )
        db.add(refund_record)

        try:
            wxpay.refund(
                out_refund_no=out_refund_no,
                transaction_id=order.wx_transaction_id,
                amount={
                    "refund": int(refund_amount * 100),
                    "total": int(order.amount * 100),
                    "currency": "CNY",
                },
                reason=req.reason or "用户取消订单",
            )
        except Exception as e:
            refund_record.fail_reason = str(e)[:500]
            if _is_refund_retryable(e):
                refund_record.status = "failed"
                refund_record.scheduled_at = datetime.utcnow() + timedelta(
                    seconds=_refund_backoff_seconds(refund_record.retry_count)
                )
                await db.commit()
                # Enqueue retry task
                from app.tasks.tasks import retry_failed_refunds
                retry_failed_refunds.delay()
                return {"msg": "Refund queued for retry", "status": "refunding", "out_refund_no": out_refund_no}
            else:
                await db.commit()
                raise HTTPException(status_code=502, detail=f"Refund request failed: {str(e)}")

        order.status = OrderStatus.refunding
        order.refund_id = out_refund_no
        order.refund_status = "pending"
        await db.commit()
        # Slot stays booked until REFUND.SUCCESS callback arrives
```

- [ ] **Step 3: Update refund_booking refund block**

Replace lines 760-796 similarly:

```python
    wxpay = get_wxpay()
    out_refund_no = _generate_order_no()

    refund_record = RefundRecord(
        order_id=order.id,
        out_refund_no=out_refund_no,
        amount=refund_amount,
        reason=req.reason or "管理员退款",
        status="pending",
    )
    db.add(refund_record)

    try:
        wxpay.refund(
            out_refund_no=out_refund_no,
            transaction_id=order.wx_transaction_id,
            amount={
                "refund": int(refund_amount * 100),
                "total": int(order.amount * 100),
                "currency": "CNY",
            },
            reason=req.reason or "管理员退款",
        )
    except Exception as e:
        refund_record.fail_reason = str(e)[:500]
        if _is_refund_retryable(e):
            refund_record.status = "failed"
            refund_record.scheduled_at = datetime.utcnow() + timedelta(
                seconds=_refund_backoff_seconds(refund_record.retry_count)
            )
            await db.commit()
            from app.tasks.tasks import retry_failed_refunds
            retry_failed_refunds.delay()
            return {"msg": "Refund queued for retry", "status": "refunding", "out_refund_no": out_refund_no}
        else:
            await db.commit()
            raise HTTPException(status_code=500, detail=f"WeChat refund failed: {str(e)}")

    order.status = OrderStatus.refunding
    order.refund_amount = refund_amount
    order.refund_id = out_refund_no
    order.refund_status = "pending"
    order.cancel_reason = req.reason or "管理员退款"
    order.cancel_time = datetime.utcnow()
    await db.commit()
```

---

## Task 4: Add Celery refund retry and polling tasks

**Files:**
- Modify: `backend/app/tasks/tasks.py`
- Modify: `backend/app/tasks/worker.py`

- [ ] **Step 1: Add helper functions**

Add to `tasks.py`:

```python
from datetime import datetime, timezone, date, time, timedelta
from sqlalchemy import select, update
from app.tasks.worker import celery_app
from app.core.database import async_session_factory
from app.core.redis import release_lock
from app.models.models import VenueTimeSlot, SlotStatus, BookingOrder, OrderStatus, RefundRecord


def _refund_backoff_seconds(attempt: int) -> int:
    from app.core.config import get_settings
    settings = get_settings()
    base = settings.REFUND_RETRY_BACKOFF_BASE_SECONDS
    return min(base * (2 ** attempt), 1800)


def _is_refund_retryable(exc: Exception) -> bool:
    import httpx
    msg = str(exc).upper()
    retryable_codes = {"SYSTEM_ERROR", "BIZERR_NEED_RETRY", "FREQUENCY_LIMITED"}
    if any(code in msg for code in retryable_codes):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    return False


async def _update_order_after_refund(session, order_id: int, status: str, refund_id: str = None):
    """Update BookingOrder status and release slot if refund succeeded."""
    result = await session.execute(
        select(BookingOrder, VenueTimeSlot)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.id == order_id)
    )
    row = result.first()
    if not row:
        return
    order, slot = row

    if status == "success":
        order.status = OrderStatus.refunded
        slot.status = SlotStatus.available
        slot.locked_by = None
        slot.locked_at = None
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key, str(order.user_id))
    elif status in ("closed", "abnormal", "failed"):
        # Revert to paid if refund did not complete
        order.status = OrderStatus.paid
        order.refund_status = status
```

- [ ] **Step 2: Add retry_failed_refunds task**

```python
@celery_app.task(name="app.tasks.tasks.retry_failed_refunds")
def retry_failed_refunds():
    """Poll for failed/pending refunds and retry them."""
    import asyncio
    from sqlalchemy import select
    from app.core.config import get_settings
    from app.core.wechat_pay import get_wxpay

    settings = get_settings()

    async def _run():
        async with async_session_factory() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(RefundRecord)
                .where(
                    RefundRecord.status.in_(["pending", "failed"]),
                    RefundRecord.scheduled_at <= now,
                    RefundRecord.retry_count < settings.REFUND_MAX_RETRIES,
                )
                .order_by(RefundRecord.scheduled_at)
                .limit(settings.REFUND_BATCH_SIZE)
            )
            records = result.scalars().all()

            processed = 0
            errors = 0
            for rec in records:
                try:
                    # Load order
                    order_result = await session.execute(
                        select(BookingOrder).where(BookingOrder.id == rec.order_id)
                    )
                    order = order_result.scalar_one_or_none()
                    if not order or not order.wx_transaction_id:
                        rec.status = "failed"
                        rec.fail_reason = "Order missing or no transaction id"
                        await session.commit()
                        processed += 1
                        continue

                    # First check current status via query API
                    wxpay = get_wxpay()
                    try:
                        query_resp = wxpay.query_refund(out_refund_no=rec.out_refund_no)
                        refund_status = query_resp.get("status")
                        if refund_status == "SUCCESS":
                            rec.status = "success"
                            rec.wx_refund_id = query_resp.get("refund_id")
                            rec.completed_at = datetime.utcnow()
                            await _update_order_after_refund(session, rec.order_id, "success", rec.out_refund_no)
                            await session.commit()
                            processed += 1
                            continue
                        elif refund_status == "PROCESSING":
                            rec.status = "processing"
                            await session.commit()
                            processed += 1
                            continue
                        elif refund_status in ("CLOSED", "ABNORMAL"):
                            rec.status = refund_status.lower()
                            await _update_order_after_refund(session, rec.order_id, rec.status, rec.out_refund_no)
                            await session.commit()
                            processed += 1
                            continue
                    except Exception:
                        # Query failed; proceed to resubmit
                        pass

                    # Resubmit refund with same out_refund_no
                    try:
                        wxpay.refund(
                            out_refund_no=rec.out_refund_no,
                            transaction_id=order.wx_transaction_id,
                            amount={
                                "refund": int(rec.amount * 100),
                                "total": int(order.amount * 100),
                                "currency": "CNY",
                            },
                            reason=rec.reason or "退款重试",
                        )
                        rec.status = "processing"
                        rec.retry_count = 0
                        rec.fail_reason = None
                        order.status = OrderStatus.refunding
                        order.refund_status = "pending"
                    except Exception as exc:
                        rec.retry_count += 1
                        rec.fail_reason = str(exc)[:500]
                        if _is_refund_retryable(exc) and rec.retry_count < settings.REFUND_MAX_RETRIES:
                            rec.status = "failed"
                            rec.scheduled_at = datetime.utcnow() + timedelta(
                                seconds=_refund_backoff_seconds(rec.retry_count)
                            )
                        else:
                            rec.status = "failed"
                            await _update_order_after_refund(session, rec.order_id, "failed", rec.out_refund_no)

                    await session.commit()
                    processed += 1
                except Exception:
                    logger.exception("Refund retry failed for record %s", rec.id)
                    await session.rollback()
                    errors += 1

            return {"processed": processed, "errors": errors}

    return asyncio.run(_run())
```

- [ ] **Step 3: Add poll_processing_refunds task**

```python
@celery_app.task(name="app.tasks.tasks.poll_processing_refunds")
def poll_processing_refunds():
    """Poll WeChat for refunds stuck in processing state."""
    import asyncio
    from sqlalchemy import select
    from app.core.wechat_pay import get_wxpay

    async def _run():
        async with async_session_factory() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(RefundRecord)
                .where(RefundRecord.status == "processing")
                .where(RefundRecord.updated_at <= now - timedelta(minutes=1))
                .limit(100)
            )
            records = result.scalars().all()

            wxpay = get_wxpay()
            for rec in records:
                try:
                    resp = wxpay.query_refund(out_refund_no=rec.out_refund_no)
                    status = resp.get("status")
                    if status == "SUCCESS":
                        rec.status = "success"
                        rec.wx_refund_id = resp.get("refund_id")
                        rec.completed_at = datetime.utcnow()
                        await _update_order_after_refund(session, rec.order_id, "success", rec.out_refund_no)
                    elif status == "PROCESSING":
                        continue
                    elif status in ("CLOSED", "ABNORMAL"):
                        rec.status = status.lower()
                        await _update_order_after_refund(session, rec.order_id, rec.status, rec.out_refund_no)
                    else:
                        rec.status = "failed"
                        rec.fail_reason = f"Unknown refund status: {status}"
                        await _update_order_after_refund(session, rec.order_id, "failed", rec.out_refund_no)
                    await session.commit()
                except Exception:
                    logger.exception("Poll refund status failed for record %s", rec.id)
                    await session.rollback()

    return asyncio.run(_run())
```

- [ ] **Step 4: Register beat schedules in worker.py**

Add to `beat_schedule`:

```python
        "retry-failed-refunds": {
            "task": "app.tasks.tasks.retry_failed_refunds",
            "schedule": 300.0,  # every 5 minutes
        },
        "poll-processing-refunds": {
            "task": "app.tasks.tasks.poll_processing_refunds",
            "schedule": crontab(minute="*/5"),
        },
```

---

## Task 5: Update fix-progress documentation

**Files:**
- Modify: `docs/module-b-fix-progress.md`

- [ ] **Step 1: Mark P1-8 as completed**

In the P1 table, update the P1-8 row to:
- Status: ✅
- 负责人: Claude
- 备注: 新增 RefundRecord 重试字段、退款前预创建记录、Celery 自动重试与轮询任务

---

## Verification

- Run `python -m py_compile backend/app/models/models.py backend/app/core/config.py backend/app/api/v1/bookings.py backend/app/tasks/tasks.py backend/app/tasks/worker.py`.
- Start the API and verify it boots without import errors.
- Verify Celery beat schedule is registered.
- Test with WeChat Pay sandbox by simulating a `SYSTEM_ERROR` refund response.
