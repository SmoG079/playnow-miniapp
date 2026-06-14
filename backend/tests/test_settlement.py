import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, call
from app.services.settlement import execute_settlement, query_settlement_status, _to_cents
from app.models.models import SettlementRecord, SettlementStatus, BookingOrder, OrderStatus, Club


class FakeResult:
    def first(self):
        return self.row

    def __init__(self, row):
        self.row = row


class FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, stmt):
        return FakeResult(self._row)


@pytest.fixture
def mock_wxpay():
    wxpay = MagicMock()
    wxpay.profitsharing_order = MagicMock(return_value={
        "order_id": "WX123",
        "state": "PROCESSING",
    })
    wxpay.profitsharing_unfreeze = MagicMock(return_value={})
    return wxpay


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.SETTLEMENT_PLATFORM_ACCOUNT = "PLATFORM_MCHID"
    settings.SETTLEMENT_MAX_RETRIES = 3
    return settings


@pytest.fixture
def base_entities():
    order = BookingOrder(
        id=1,
        order_no="ORD001",
        user_id=1,
        venue_id=1,
        slot_id=1,
        club_id=1,
        amount=Decimal("10.00"),
        status=OrderStatus.paid,
        wx_transaction_id="TX123",
    )
    settlement = SettlementRecord(
        id=1,
        order_id=1,
        total_amount=Decimal("10.00"),
        club_amount=Decimal("9.00"),
        platform_amount=Decimal("1.00"),
        split_ratio=Decimal("0.100"),
        status=SettlementStatus.pending,
        scheduled_at=datetime.utcnow(),
    )
    club = Club(
        id=1,
        name="Test Club",
        sport_types=["badminton"],
        split_ratio=Decimal("0.100"),
        sub_merchant_id="SUB123",
    )
    return settlement, order, club


# ---------------------------------------------------------------------------
# P1-5: unfreeze_unsplit=False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profitsharing_order_called_with_unfreeze_unsplit_false(mock_wxpay, mock_settings, base_entities):
    """
    P1-5: profitsharing_order must be called with unfreeze_unsplit=False
    so funds remain frozen while the order is in progress.
    """
    settlement, order, club = base_entities
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        await execute_settlement(session, settlement_id=1)

    call_kwargs = mock_wxpay.profitsharing_order.call_args.kwargs
    assert call_kwargs["unfreeze_unsplit"] is False, (
        f"Expected unfreeze_unsplit=False, got {call_kwargs.get('unfreeze_unsplit')}"
    )


@pytest.mark.asyncio
async def test_unfreeze_called_when_immediate_finished_all_success(mock_wxpay, mock_settings, base_entities):
    """
    P1-5: When execute_settlement gets an immediate FINISHED with all SUCCESS,
    profitsharing_unfreeze must be called.
    """
    settlement, order, club = base_entities
    mock_wxpay.profitsharing_order = MagicMock(return_value={
        "order_id": "WX123",
        "state": "FINISHED",
        "receivers": [
            {"result": "SUCCESS"},
            {"result": "SUCCESS"},
        ],
    })
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=1)

    assert result.status == SettlementStatus.completed
    mock_wxpay.profitsharing_unfreeze.assert_called_once()
    call_kwargs = mock_wxpay.profitsharing_unfreeze.call_args.kwargs
    assert call_kwargs["transaction_id"] == "TX123"
    assert call_kwargs["out_order_no"] == settlement.out_order_no
    assert call_kwargs["sub_mchid"] == "SUB123"
    assert "description" in call_kwargs


@pytest.mark.asyncio
async def test_unfreeze_not_called_when_finished_with_failure(mock_wxpay, mock_settings, base_entities):
    """
    P1-5: When profit-sharing finishes but not all receivers SUCCESS,
    unfreeze must NOT be called because the order failed.
    """
    settlement, order, club = base_entities
    mock_wxpay.profitsharing_order = MagicMock(return_value={
        "order_id": "WX123",
        "state": "FINISHED",
        "receivers": [
            {"result": "SUCCESS"},
            {"result": "FAIL"},
        ],
    })
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=1)

    assert result.status == SettlementStatus.failed
    mock_wxpay.profitsharing_unfreeze.assert_not_called()


@pytest.mark.asyncio
async def test_unfreeze_not_called_when_processing(mock_wxpay, mock_settings, base_entities):
    """
    P1-5: When profit-sharing is PROCESSING, unfreeze must NOT be called yet.
    """
    settlement, order, club = base_entities
    mock_wxpay.profitsharing_order = MagicMock(return_value={
        "order_id": "WX123",
        "state": "PROCESSING",
    })
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=1)

    assert result.status == SettlementStatus.processing
    mock_wxpay.profitsharing_unfreeze.assert_not_called()


@pytest.mark.asyncio
async def test_unfreeze_called_when_query_finishes_all_success(mock_wxpay, mock_settings, base_entities):
    """
    P1-5: When query_settlement_status polls and finds FINISHED+all SUCCESS,
    profitsharing_unfreeze must be called.
    """
    settlement, order, club = base_entities
    settlement.status = SettlementStatus.processing
    settlement.out_order_no = "PSORD001"
    mock_wxpay.profitsharing_order_query = MagicMock(return_value={
        "state": "FINISHED",
        "receivers": [
            {"result": "SUCCESS"},
            {"result": "SUCCESS"},
        ],
    })
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await query_settlement_status(session, settlement_id=1)

    assert result.status == SettlementStatus.completed
    mock_wxpay.profitsharing_unfreeze.assert_called_once()
    call_kwargs = mock_wxpay.profitsharing_unfreeze.call_args.kwargs
    assert call_kwargs["transaction_id"] == "TX123"
    assert call_kwargs["out_order_no"] == "PSORD001"
    assert call_kwargs["sub_mchid"] == "SUB123"


@pytest.mark.asyncio
async def test_unfreeze_not_called_when_query_finishes_with_failure(mock_wxpay, mock_settings, base_entities):
    """
    P1-5: When query finds FINISHED but not all receivers SUCCESS,
    unfreeze must NOT be called.
    """
    settlement, order, club = base_entities
    settlement.status = SettlementStatus.processing
    settlement.out_order_no = "PSORD001"
    mock_wxpay.profitsharing_order_query = MagicMock(return_value={
        "state": "FINISHED",
        "receivers": [
            {"result": "SUCCESS"},
            {"result": "FAIL"},
        ],
    })
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await query_settlement_status(session, settlement_id=1)

    assert result.status == SettlementStatus.failed
    mock_wxpay.profitsharing_unfreeze.assert_not_called()


@pytest.mark.asyncio
async def test_unfreeze_failure_does_not_revert_completed_status(mock_wxpay, mock_settings, base_entities, caplog):
    """
    P1-5: If profitsharing_unfreeze raises an exception, the settlement must
    stay completed and the failure reason should be recorded separately.
    """
    settlement, order, club = base_entities
    mock_wxpay.profitsharing_order = MagicMock(return_value={
        "order_id": "WX123",
        "state": "FINISHED",
        "receivers": [
            {"result": "SUCCESS"},
            {"result": "SUCCESS"},
        ],
    })
    mock_wxpay.profitsharing_unfreeze = MagicMock(side_effect=Exception("WeChat API timeout"))
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=1)

    assert result.status == SettlementStatus.completed
    assert result.fail_reason and "unfreeze" in result.fail_reason.lower()


@pytest.mark.asyncio
async def test_unfreeze_failure_in_query_does_not_revert_completed(mock_wxpay, mock_settings, base_entities, caplog):
    """
    P1-5: If profitsharing_unfreeze raises during query_settlement_status,
    the settlement must stay completed and record the unfreeze failure.
    """
    settlement, order, club = base_entities
    settlement.status = SettlementStatus.processing
    settlement.out_order_no = "PSORD001"
    mock_wxpay.profitsharing_order_query = MagicMock(return_value={
        "state": "FINISHED",
        "receivers": [
            {"result": "SUCCESS"},
            {"result": "SUCCESS"},
        ],
    })
    mock_wxpay.profitsharing_unfreeze = MagicMock(side_effect=Exception("WeChat API timeout"))
    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await query_settlement_status(session, settlement_id=1)

    assert result.status == SettlementStatus.completed
    assert result.fail_reason and "unfreeze" in result.fail_reason.lower()


# ---------------------------------------------------------------------------
# P1-6: existing receiver adjustment tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adjusted_receiver_cents_synced_to_settlement_fields(mock_wxpay, mock_settings):
    """
    P1-6: When a 1-cent rounding difference is adjusted, the adjusted cents
    must be written back to settlement.club_amount and settlement.platform_amount.
    """
    # Create a scenario where club_amount + platform_amount in cents
    # is 1 cent less than order.amount in cents.
    # order.amount = 10.00 -> 1000 cents
    # club_amount = 9.00 -> 900 cents
    # platform_amount = 0.99 -> 99 cents
    # sum = 999 cents, diff = +1 cent -> larger receiver (club) gets adjusted
    order = BookingOrder(
        id=1,
        order_no="ORD001",
        user_id=1,
        venue_id=1,
        slot_id=1,
        club_id=1,
        amount=Decimal("10.00"),
        status=OrderStatus.paid,
        wx_transaction_id="TX123",
    )
    settlement = SettlementRecord(
        id=1,
        order_id=1,
        total_amount=Decimal("10.00"),
        club_amount=Decimal("9.00"),
        platform_amount=Decimal("0.99"),
        split_ratio=Decimal("0.100"),
        status=SettlementStatus.pending,
        scheduled_at=datetime.utcnow(),
    )
    club = Club(
        id=1,
        name="Test Club",
        sport_types=["badminton"],
        split_ratio=Decimal("0.100"),
        sub_merchant_id="SUB123",
    )

    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=1)

    # After adjustment, the larger receiver (club) should get the +1 cent
    assert result.club_amount == Decimal("9.01"), (
        f"Expected club_amount to be adjusted to 9.01, got {result.club_amount}"
    )
    assert result.platform_amount == Decimal("0.99"), (
        f"Expected platform_amount unchanged at 0.99, got {result.platform_amount}"
    )
    # The total must still equal order.amount
    assert result.club_amount + result.platform_amount == order.amount, (
        f"Adjusted total {result.club_amount + result.platform_amount} != {order.amount}"
    )

    # Verify the WeChat API was called with the adjusted cents
    call_kwargs = mock_wxpay.profitsharing_order.call_args.kwargs
    receivers = call_kwargs["receivers"]
    assert len(receivers) == 2
    club_receiver = next(r for r in receivers if r["account"] == "SUB123")
    platform_receiver = next(r for r in receivers if r["account"] == "PLATFORM_MCHID")
    assert club_receiver["amount"] == 901  # 9.01 * 100
    assert platform_receiver["amount"] == 99  # 0.99 * 100


@pytest.mark.asyncio
async def test_adjusted_platform_receiver_cents_synced(mock_wxpay, mock_settings):
    """
    When platform is the larger receiver and gets adjusted, sync to DB.
    """
    order = BookingOrder(
        id=2,
        order_no="ORD002",
        user_id=1,
        venue_id=1,
        slot_id=1,
        club_id=1,
        amount=Decimal("10.00"),
        status=OrderStatus.paid,
        wx_transaction_id="TX456",
    )
    settlement = SettlementRecord(
        id=2,
        order_id=2,
        total_amount=Decimal("10.00"),
        club_amount=Decimal("0.99"),
        platform_amount=Decimal("9.00"),
        split_ratio=Decimal("0.900"),
        status=SettlementStatus.pending,
        scheduled_at=datetime.utcnow(),
    )
    club = Club(
        id=1,
        name="Test Club",
        sport_types=["badminton"],
        split_ratio=Decimal("0.900"),
        sub_merchant_id="SUB123",
    )

    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=2)

    # platform is larger (900 > 99), so platform gets +1 cent
    assert result.platform_amount == Decimal("9.01"), (
        f"Expected platform_amount to be adjusted to 9.01, got {result.platform_amount}"
    )
    assert result.club_amount == Decimal("0.99"), (
        f"Expected club_amount unchanged at 0.99, got {result.club_amount}"
    )
    assert result.club_amount + result.platform_amount == order.amount


@pytest.mark.asyncio
async def test_no_adjustment_when_sum_matches(mock_wxpay, mock_settings):
    """
    When there is no rounding mismatch, amounts should remain unchanged.
    """
    order = BookingOrder(
        id=3,
        order_no="ORD003",
        user_id=1,
        venue_id=1,
        slot_id=1,
        club_id=1,
        amount=Decimal("10.00"),
        status=OrderStatus.paid,
        wx_transaction_id="TX789",
    )
    settlement = SettlementRecord(
        id=3,
        order_id=3,
        total_amount=Decimal("10.00"),
        club_amount=Decimal("9.00"),
        platform_amount=Decimal("1.00"),
        split_ratio=Decimal("0.100"),
        status=SettlementStatus.pending,
        scheduled_at=datetime.utcnow(),
    )
    club = Club(
        id=1,
        name="Test Club",
        sport_types=["badminton"],
        split_ratio=Decimal("0.100"),
        sub_merchant_id="SUB123",
    )

    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=3)

    assert result.club_amount == Decimal("9.00")
    assert result.platform_amount == Decimal("1.00")
    assert result.club_amount + result.platform_amount == order.amount


@pytest.mark.asyncio
async def test_only_club_receiver_adjusted(mock_wxpay, mock_settings):
    """
    When only club receiver is present and there is a mismatch, adjust club.
    """
    order = BookingOrder(
        id=4,
        order_no="ORD004",
        user_id=1,
        venue_id=1,
        slot_id=1,
        club_id=1,
        amount=Decimal("10.00"),
        status=OrderStatus.paid,
        wx_transaction_id="TX999",
    )
    settlement = SettlementRecord(
        id=4,
        order_id=4,
        total_amount=Decimal("10.00"),
        club_amount=Decimal("9.99"),
        platform_amount=Decimal("0.00"),
        split_ratio=Decimal("0.000"),
        status=SettlementStatus.pending,
        scheduled_at=datetime.utcnow(),
    )
    club = Club(
        id=1,
        name="Test Club",
        sport_types=["badminton"],
        split_ratio=Decimal("0.000"),
        sub_merchant_id="SUB123",
    )

    session = FakeSession((settlement, order, club))

    with patch("app.services.settlement.get_wxpay", return_value=mock_wxpay), \
         patch("app.services.settlement.get_settings", return_value=mock_settings):
        result = await execute_settlement(session, settlement_id=4)

    # Only club receiver present, gets adjusted by +1 cent
    assert result.club_amount == Decimal("10.00"), (
        f"Expected club_amount adjusted to 10.00, got {result.club_amount}"
    )
    assert result.platform_amount == Decimal("0.00")
    assert result.club_amount + result.platform_amount == order.amount

    call_kwargs = mock_wxpay.profitsharing_order.call_args.kwargs
    receivers = call_kwargs["receivers"]
    assert len(receivers) == 1
    assert receivers[0]["amount"] == 1000
