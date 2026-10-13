"""Registration expiry is a listing rule, not event cancellation or data deletion."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import and_, or_, func, case
from app.models.models import MatchPost, Tournament


def registration_closed_condition(kind, now):
    if kind == "tournament":
        return or_(Tournament.registration_closed.is_(True),
            Tournament.status.in_(["cancelled", "finished", "ongoing"]),
            func.coalesce(Tournament.registration_deadline, Tournament.start_time) <= now,
            Tournament.start_time <= now)
    local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
    return or_(MatchPost.status == "closed", MatchPost.preferred_date < local.date(),
        and_(MatchPost.preferred_date == local.date(), MatchPost.preferred_start <= local.time().replace(tzinfo=None)))


def public_listing_condition(kind, now):
    if kind == "tournament":
        return and_(Tournament.status.in_(["open", "ongoing"]), Tournament.end_time > now)
    return and_(MatchPost.status != "closed", MatchPost.preferred_date.is_not(None),
        MatchPost.preferred_start.is_not(None), ~registration_closed_condition(kind, now))


def post_registration_closed(post, now=None):
    now = now or datetime.utcnow()
    local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
    if not post.preferred_date or not post.preferred_start:
        return True
    return (post.preferred_date, post.preferred_start) <= (local.date(), local.time().replace(tzinfo=None))


def tournament_phase_condition(now):
    return case((Tournament.status.in_(["finished", "cancelled"]), "ended"),
        (Tournament.end_time <= now, "ended"), (Tournament.start_time <= now, "ongoing"),
        (registration_closed_condition("tournament", now), "registration_closed"), else_="open")


def tournament_phase(tournament, now=None):
    now = now or datetime.utcnow()
    if tournament.status in ("finished", "cancelled") or tournament.end_time <= now:
        return "ended"
    if tournament.start_time <= now:
        return "ongoing"
    if tournament.registration_closed or (tournament.registration_deadline or tournament.start_time) <= now or tournament.status == "ongoing":
        return "registration_closed"
    return "open"
