"""Durable recovery of admissions, payments and tournament refunds."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import _v
from app.core.config import get_settings
from app.models.models import BookingOrder, RefundRecord, Tournament
from app.services import tournament_lifecycle as life
from app.services.settlement import _to_cents


async def maintain(session_factory=None):
    settings = get_settings()
    engine = None
    if session_factory is None:
        # Celery invokes asyncio.run per task; never reuse pooled connections
        # belonging to a previous event loop.
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            return await maintain_db(db, settings)
    finally:
        if engine is not None:
            await engine.dispose()


async def maintain_db(db, settings):
    processed = errors = 0
    ids = list(
        (
            await db.execute(
                select(Tournament.id).where(
                    Tournament.config.isnot(None),
                    Tournament.status.in_(["open", "ongoing"]),
                )
            )
        ).scalars()
    )
    await db.rollback()
    for ident in ids:
        try:
            t = await life.locked_event(db, ident)
            await life.refresh_admissions(db, t)
            await db.commit()
        except Exception:
            errors += 1
            await db.rollback()
            life.logger.error(
                "Tournament admission recovery failed: %s", ident, exc_info=True
            )

    orders = (
        await db.execute(
            select(BookingOrder.id, BookingOrder.tournament_id)
            .where(
                BookingOrder.business_type == "tournament",
                BookingOrder.status == "pending",
            )
            .limit(100)
        )
    ).all()
    await db.rollback()
    for ident, event_id in orders:
        try:
            t = await life.locked_event(db, event_id)
            o = await life.locked_order(db, ident)
            if _v(o.status) != "pending":
                await db.rollback()
                continue
            rows = await life.refresh_admissions(db, t)
            reg = next((r for r in rows if r.order_id == o.id), None)
            response = await life.wx_call("query", out_trade_no=o.order_no)
            state = response.get("trade_state")
            if state == "SUCCESS":
                await life.payment_success(db, response)
            elif (
                state in ("CLOSED", "REVOKED")
                or not reg
                or reg.admission != "active"
                or t.registration_closed
            ):
                if state not in ("CLOSED", "REVOKED"):
                    await life.wx_call("close", out_trade_no=o.order_no)
                await life.payment_closed(db, {"out_trade_no": o.order_no})
            await db.commit()
            processed += 1
        except Exception:
            errors += 1
            await db.rollback()
            life.logger.error(
                "Tournament payment recovery failed: %s", ident, exc_info=True
            )

    refs = (
        await db.execute(
            select(RefundRecord.id, BookingOrder.id, BookingOrder.tournament_id)
            .join(BookingOrder, RefundRecord.order_id == BookingOrder.id)
            .where(
                BookingOrder.business_type == "tournament",
                RefundRecord.status.in_(["pending", "failed", "processing"]),
                RefundRecord.scheduled_at <= life.now(),
                RefundRecord.retry_count < settings.REFUND_MAX_RETRIES,
            )
            .limit(settings.REFUND_BATCH_SIZE)
        )
    ).all()
    await db.rollback()
    for ident, order_id, event_id in refs:
        try:
            await life.locked_event(db, event_id)
            o = await life.locked_order(db, order_id)
            ref = (
                await db.execute(
                    select(RefundRecord)
                    .where(RefundRecord.id == ident)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            if _v(ref.status) not in ("pending", "failed", "processing"):
                await db.rollback()
                continue
            if not o.wx_transaction_id or o.wx_transaction_id.startswith("dev_"):
                raise RuntimeError("Unverified historical payment")
            if _v(ref.status) == "processing":
                response = await life.wx_call(
                    "query_refund", out_refund_no=ref.out_refund_no
                )
            else:
                paid = await life.wx_call("query", out_trade_no=o.order_no)
                if (
                    paid.get("trade_state") != "SUCCESS"
                    or paid.get("transaction_id") != o.wx_transaction_id
                    or paid.get("mchid") != settings.WX_MCH_ID
                    or paid.get("appid") != settings.WX_APP_ID
                    or paid.get("amount", {}).get("total") != _to_cents(o.amount)
                ):
                    raise RuntimeError("Payment query does not match refundable order")
                response = await life.wx_call(
                    "refund",
                    out_refund_no=ref.out_refund_no,
                    transaction_id=o.wx_transaction_id,
                    amount={
                        "refund": _to_cents(ref.amount),
                        "total": _to_cents(o.amount),
                        "currency": "CNY",
                    },
                    reason=ref.reason,
                )
            state = response.get("status", "").lower()
            if (
                state not in ("success", "processing", "closed", "abnormal")
                or response.get("out_refund_no") != ref.out_refund_no
                or response.get("out_trade_no") != o.order_no
                or response.get("amount", {}).get("refund") != _to_cents(ref.amount)
            ):
                raise RuntimeError("Refund response does not match order")
            await life.refund_callback(
                db,
                dict(
                    response,
                    refund_status=state.upper(),
                    mchid=response.get("mchid", settings.WX_MCH_ID),
                ),
            )
            ref.scheduled_at = life.now() + timedelta(
                minutes=settings.REFUND_POLL_INTERVAL_MINUTES
            )
            await db.commit()
            processed += 1
        except Exception:
            await db.rollback()
            errors += 1
            await life.locked_event(db, event_id)
            ref = (
                await db.execute(
                    select(RefundRecord)
                    .where(RefundRecord.id == ident)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            # A callback may have succeeded while the remote request failed.
            if _v(ref.status) != "success":
                ref.retry_count += 1
                ref.status = "failed"
                ref.fail_reason = "微信退款处理失败，请查询后重试"
                ref.scheduled_at = life.now() + timedelta(
                    seconds=min(
                        settings.REFUND_RETRY_BACKOFF_BASE_SECONDS * 2**ref.retry_count,
                        1800,
                    )
                )
            await db.commit()
            life.logger.error(
                "Tournament refund recovery failed: %s", ident, exc_info=True
            )
    return {"processed": processed, "errors": errors}
