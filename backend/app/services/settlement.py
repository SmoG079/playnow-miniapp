import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.wechat_pay import get_wxpay
from app.models.models import SettlementRecord, SettlementStatus, BookingOrder, OrderStatus, Club

logger = logging.getLogger(__name__)


def _to_cents(amount: Decimal) -> int:
    """Convert a Decimal amount to integer cents (1 yuan = 100 cents)."""
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def generate_settlement_out_order_no(order_no: str) -> str:
    """Generate the out_order_no for a profit-sharing order."""
    return f"PS{order_no}"


async def execute_settlement(session: AsyncSession, settlement_id: int) -> SettlementRecord:
    """Call WeChat profit-sharing API for a pending settlement record.

    This function does NOT commit; the caller is responsible for the transaction boundary.
    """
    settings = get_settings()
    wxpay = get_wxpay()

    result = await session.execute(
        select(SettlementRecord, BookingOrder, Club)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .join(Club, BookingOrder.club_id == Club.id)
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
        return settlement

    if not order.wx_transaction_id:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "Missing wx_transaction_id"
        return settlement

    if not club.sub_merchant_id:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "Club missing sub_merchant_id"
        return settlement

    if not settings.SETTLEMENT_PLATFORM_ACCOUNT:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "SETTLEMENT_PLATFORM_ACCOUNT not configured"
        return settlement

    if not settlement.out_order_no:
        settlement.out_order_no = generate_settlement_out_order_no(order.order_no)

    # Build receivers list, filtering out zero-amount entries
    receivers = []
    club_amount_cents = _to_cents(settlement.club_amount)
    if club_amount_cents > 0:
        receivers.append({
            "type": "MERCHANT_ID",
            "account": club.sub_merchant_id,
            "amount": club_amount_cents,
            "currency": "CNY",
            "description": "场地预约分账",
        })

    platform_amount_cents = _to_cents(settlement.platform_amount)
    if platform_amount_cents > 0:
        receivers.append({
            "type": "MERCHANT_ID",
            "account": settings.SETTLEMENT_PLATFORM_ACCOUNT,
            "amount": platform_amount_cents,
            "currency": "CNY",
            "description": "平台服务费",
        })

    if not receivers:
        # Nothing to split - mark as completed immediately
        settlement.status = SettlementStatus.completed
        settlement.completed_at = datetime.utcnow()
        settlement.retry_count = 0
        settlement.fail_reason = None
        logger.info("Settlement %s has zero amounts for all receivers; marked completed", settlement.id)
        return settlement

    # Validate receiver amount sum matches order total exactly
    order_total_cents = _to_cents(order.amount)
    receiver_sum = club_amount_cents + platform_amount_cents
    if receiver_sum != order_total_cents:
        diff = order_total_cents - receiver_sum
        logger.warning(
            "Settlement %s receiver sum mismatch: %d != %d (diff=%d). Adjusting larger receiver.",
            settlement.id, receiver_sum, order_total_cents, diff,
        )
        if club_amount_cents >= platform_amount_cents:
            club_amount_cents += diff
            settlement.club_amount = Decimal(club_amount_cents) / Decimal("100")
            # Update the receiver dict in place
            for r in receivers:
                if r["account"] == club.sub_merchant_id:
                    r["amount"] = club_amount_cents
                    break
        else:
            platform_amount_cents += diff
            settlement.platform_amount = Decimal(platform_amount_cents) / Decimal("100")
            # Update the receiver dict in place
            for r in receivers:
                if r["account"] == settings.SETTLEMENT_PLATFORM_ACCOUNT:
                    r["amount"] = platform_amount_cents
                    break

    logger.debug(
        "Settlement %s profit-sharing receivers: %s", settlement.id, receivers,
    )

    try:
        resp = wxpay.profitsharing_order(
            transaction_id=order.wx_transaction_id,
            out_order_no=settlement.out_order_no,
            receivers=receivers,
            unfreeze_unsplit=False,
            sub_mchid=club.sub_merchant_id,
        )
        settlement.wx_split_order_no = resp.get("order_id")

        state = resp.get("state")
        if state == "PROCESSING":
            settlement.status = SettlementStatus.processing
            settlement.retry_count = 0
            settlement.fail_reason = None
            logger.info("Profit-sharing order created (PROCESSING): %s", settlement.wx_split_order_no)
        elif state == "FINISHED":
            resp_receivers = resp.get("receivers", [])
            if all(r.get("result") == "SUCCESS" for r in resp_receivers):
                settlement.status = SettlementStatus.completed
                settlement.completed_at = datetime.utcnow()
                settlement.retry_count = 0
                settlement.fail_reason = None
                logger.info("Profit-sharing order finished (SUCCESS): %s", settlement.wx_split_order_no)
                # Unfreeze remaining unsplit funds now that profit-sharing is confirmed
                try:
                    await wxpay.profitsharing_unfreeze(
                        transaction_id=order.wx_transaction_id,
                        out_order_no=settlement.out_order_no,
                        description="解冻剩余未分账资金",
                        sub_mchid=club.sub_merchant_id,
                    )
                    logger.info("Unfreeze unsplit funds succeeded for settlement %s", settlement.id)
                except Exception as unfreeze_exc:
                    settlement.fail_reason = f"Unfreeze failed: {unfreeze_exc}"[:500]
                    logger.exception("Unfreeze unsplit funds failed for settlement %s", settlement.id)
            else:
                settlement.status = SettlementStatus.failed
                settlement.retry_count = (settlement.retry_count or 0) + 1
                settlement.fail_reason = f"state=FINISHED but not all receivers SUCCESS: {resp}"
                logger.error("Profit-sharing finished with failures: %s", resp)
        else:
            settlement.status = SettlementStatus.failed
            settlement.retry_count = (settlement.retry_count or 0) + 1
            settlement.fail_reason = f"Unexpected state={state}, response={resp}"
            logger.error("Unexpected profit-sharing state: %s", resp)
    except Exception as exc:
        settlement.retry_count = (settlement.retry_count or 0) + 1
        if settlement.retry_count >= settings.SETTLEMENT_MAX_RETRIES:
            settlement.status = SettlementStatus.failed
        else:
            settlement.status = SettlementStatus.pending
        settlement.fail_reason = str(exc)[:500]
        logger.exception("Profit-sharing order failed for settlement %s", settlement.id)

    return settlement


async def query_settlement_status(session: AsyncSession, settlement_id: int) -> SettlementRecord:
    """Query WeChat for current profit-sharing status and update the record.

    This function does NOT commit; the caller is responsible for the transaction boundary.
    """
    wxpay = get_wxpay()

    result = await session.execute(
        select(SettlementRecord, BookingOrder, Club)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .join(Club, BookingOrder.club_id == Club.id)
        .where(SettlementRecord.id == settlement_id)
    )
    row = result.first()
    if not row:
        raise ValueError(f"Settlement {settlement_id} not found")

    settlement, order, club = row

    if settlement.status in (SettlementStatus.completed, SettlementStatus.failed):
        return settlement

    if not settlement.out_order_no or not order.wx_transaction_id:
        settlement.status = SettlementStatus.failed
        settlement.fail_reason = "Missing out_order_no or transaction_id"
        return settlement

    try:
        resp = wxpay.profitsharing_order_query(
            transaction_id=order.wx_transaction_id,
            out_order_no=settlement.out_order_no,
            sub_mchid=club.sub_merchant_id,
        )
        state = resp.get("state")
        receivers = resp.get("receivers", [])

        if state == "FINISHED" and all(r.get("result") == "SUCCESS" for r in receivers):
            settlement.status = SettlementStatus.completed
            settlement.completed_at = datetime.utcnow()
            settlement.retry_count = 0
            settlement.fail_reason = None
            # Unfreeze remaining unsplit funds now that profit-sharing is confirmed
            try:
                await wxpay.profitsharing_unfreeze(
                    transaction_id=order.wx_transaction_id,
                    out_order_no=settlement.out_order_no,
                    description="解冻剩余未分账资金",
                    sub_mchid=club.sub_merchant_id,
                )
                logger.info("Unfreeze unsplit funds succeeded for settlement %s", settlement.id)
            except Exception as unfreeze_exc:
                settlement.fail_reason = f"Unfreeze failed: {unfreeze_exc}"[:500]
                logger.exception("Unfreeze unsplit funds failed for settlement %s", settlement.id)
        elif state == "FINISHED":
            settlement.status = SettlementStatus.failed
            settlement.retry_count = (settlement.retry_count or 0) + 1
            settlement.fail_reason = f"state=FINISHED but not all receivers SUCCESS: {receivers}"
        elif state == "PROCESSING":
            settlement.status = SettlementStatus.processing
        else:
            settlement.status = SettlementStatus.failed
            settlement.retry_count = (settlement.retry_count or 0) + 1
            settlement.fail_reason = f"state={state}, receivers={receivers}"

    except Exception as exc:
        logger.exception("Settlement status query failed for %s", settlement.id)
        settlement.fail_reason = f"query error: {exc}"[:500]

    return settlement
