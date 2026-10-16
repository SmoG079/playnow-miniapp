"""Parse a complete UTR source snapshot and persist one record per WeChat user ID."""
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import User, UserUtrRecord


@dataclass(frozen=True)
class UtrSnapshot:
    rating: Decimal | None
    matches_played: int | None
    wins: int | None
    losses: int | None
    world_rank: int | None
    age_group: str | None


def _number(value: Any, field: str, *, integer: bool = False, minimum: int = 0) -> Decimal | int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"Invalid UTR {field}")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"Invalid UTR {field}") from None
    maximum = Decimal(2147483647) if integer else Decimal('99.99')
    if not number.is_finite() or not minimum <= number <= maximum:
        raise ValueError(f"Invalid UTR {field}")
    if integer:
        if number != number.to_integral_value():
            raise ValueError(f"UTR {field} must be an integer")
        return int(number)
    if number != number.quantize(Decimal('.01')):
        raise ValueError('UTR rating supports at most two decimal places')
    return number.quantize(Decimal('.01'))


def parse_utr_snapshot(payload: Mapping[str, Any]) -> UtrSnapshot:
    """Source keys are label/lose/played/rank/rating/won; null/blank stays null.

    Import a complete snapshot: require all keys so a partial or misspelled response
    cannot silently erase previously stored values. Never derive counts or ratings.
    """
    required = {'label', 'lose', 'played', 'rank', 'rating', 'won'}
    if not isinstance(payload, Mapping) or not required.issubset(payload):
        raise ValueError('Incomplete UTR snapshot: label/lose/played/rank/rating/won required')
    label = payload['label']
    if label is not None:
        if not isinstance(label, str) or len(label.strip()) > 32:
            raise ValueError('Invalid UTR age-group label')
        label = label.strip() or None
    return UtrSnapshot(
        rating=_number(payload['rating'], 'rating'),
        matches_played=_number(payload['played'], 'played', integer=True),
        wins=_number(payload['won'], 'won', integer=True),
        losses=_number(payload['lose'], 'lose', integer=True),
        world_rank=_number(payload['rank'], 'rank', integer=True, minimum=1),
        age_group=label,
    )


async def import_utr_snapshot(db: AsyncSession, user_id: str, payload: Mapping[str, Any]) -> UserUtrRecord:
    """Caller commits. Lock the canonical users.id row to serialize concurrent imports."""
    snapshot = parse_utr_snapshot(payload)
    user = await db.get(User, user_id, with_for_update=True)
    if user is None:
        raise ValueError('UTR target user does not exist')
    record = await db.get(UserUtrRecord, user.id)
    if record is None:
        record = UserUtrRecord(user_id=user.id)
        db.add(record)
    # Keep existing canonical rating storage, with NTRP independent and untouched.
    user.utr_rating = snapshot.rating
    for field in ('matches_played', 'wins', 'losses', 'world_rank', 'age_group'):
        setattr(record, field, getattr(snapshot, field))
    await db.flush()
    return record
