from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.api.v1 import tournaments as api, messages, posts
from app.models.models import User, TournamentRegistration, Activity, MatchPost, MatchRegistration
from app.schemas.tournament import TournamentConfig, RegistrationCommand, DrawCommand, ReasonCommand, ReviewCommand
from app.services import tournament_lifecycle as life, tournament_entries as entries
from tests.test_tournaments import db, event, register


def test_doubles_pairing_policy_is_required():
    for discipline in ("doubles", "mixed"):
        with pytest.raises(ValueError, match="搭档方式"):
            TournamentConfig(discipline=discipline)
        assert TournamentConfig(discipline=discipline, pairing="fixed").pairing == "fixed"
    assert TournamentConfig(pairing="fixed").pairing is None


@pytest.mark.asyncio
async def test_fixed_roster_created_empty_and_draw_preserves_selected_teams(db, monkeypatch):
    tid, admin = await event(db, 8, TournamentConfig(discipline="doubles", pairing="fixed"))
    roster = (await api.get_tournament(tid, None, db))["entry_teams"]
    assert len(roster) == 4 and all(len(t["seats"]) == 2 for t in roster)
    assert all(not s["occupied"] for t in roster for s in t["seats"])
    chosen = [(roster[2], 2, 2), (roster[0], 1, 3), (roster[2], 1, 4), (roster[0], 2, 5)]
    for team, seat, uid in chosen:
        await register(db, tid, uid, entry_team_id=team["id"], entry_seat=seat)
    before = {frozenset(("2", "4")), frozenset(("3", "5"))}
    await api.close_registration(tid, admin, db)
    async def no_pairing(*args, **kwargs): raise AssertionError("draw must not assign seats")
    monkeypatch.setattr(entries, "claim", no_pairing)
    await api.create_draw(tid, DrawCommand(idempotency_key="entry-team-draw", publish=True), admin, db)
    detail = await api.get_tournament(tid, None, db)
    assert {frozenset(t["user_ids"]) for t in detail["teams"]} == before
    assert len(detail["entry_teams"]) == 4


@pytest.mark.asyncio
async def test_unfinished_team_blocks_draw_and_fixed_seat_cannot_be_stolen(db):
    tid, admin = await event(db, 4, TournamentConfig(discipline="doubles", pairing="fixed"))
    first = (await api.get_tournament(tid, None, db))["entry_teams"][0]
    await register(db, tid, 2, entry_team_id=first["id"], entry_seat=1)
    with pytest.raises(HTTPException) as error:
        async with db.begin_nested():
            await register(db, tid, 3, entry_team_id=first["id"], entry_seat=1)
    assert error.value.status_code == 409
    await api.close_registration(tid, admin, db)
    with pytest.raises(HTTPException, match="尚未组队完成"):
        await api.create_draw(tid, DrawCommand(idempotency_key="incomplete-team"), admin, db)


@pytest.mark.asyncio
async def test_review_holds_slot_privately_and_rejection_releases_it(db):
    tid, admin = await event(db, 4, TournamentConfig(discipline="doubles", pairing="fixed", approval_required=True))
    team = (await api.get_tournament(tid, None, db))["entry_teams"][0]
    await register(db, tid, 2, entry_team_id=team["id"], entry_seat=1)
    public = (await api.get_tournament(tid, None, db))["entry_teams"][0]["seats"][0]
    assert public["occupied"] and public["participant"] is None
    r = await api.own(db, await life.locked_event(db, tid), await db.get(User, 2))
    await api.review(tid, r.id, ReviewCommand(approved=False, reason="不符合要求"), admin, db)
    assert r.entry_team_id is None and r.entry_seat is None
    await register(db, tid, 3, entry_team_id=team["id"], entry_seat=1)


@pytest.mark.asyncio
async def test_mixed_gender_and_cross_event_seats_are_enforced(db):
    cfg = TournamentConfig(discipline="mixed", pairing="fixed")
    tid, _ = await event(db, 4, cfg)
    other, _ = await event(db, 4, cfg)
    team = (await api.get_tournament(tid, None, db))["entry_teams"][0]
    foreign = (await api.get_tournament(other, None, db))["entry_teams"][0]
    for ident, gender, seat in ((team["id"], "female", 1), (foreign["id"], "male", 1)):
        with pytest.raises(HTTPException) as error:
            async with db.begin_nested(): await register(db, tid, 2, gender=gender, entry_team_id=ident, entry_seat=seat)
        assert error.value.status_code == 422
    await register(db, tid, 2, gender="male", entry_team_id=team["id"], entry_seat=1)
    await register(db, tid, 3, gender="female", entry_team_id=team["id"], entry_seat=2)
    a = await api.own(db, await life.locked_event(db, tid), await db.get(User, 2))
    assert a.partner_user_id == "3"


@pytest.mark.asyncio
async def test_paid_seat_expires_and_single_teams_are_one_person(db, monkeypatch):
    from datetime import timedelta
    monkeypatch.setattr(life.get_settings(), "TOURNAMENT_PREPAY_ENABLED", True)
    tid, _ = await event(db, 4, TournamentConfig(discipline="doubles", pairing="fixed"), fee=20)
    team = (await api.get_tournament(tid, None, db))["entry_teams"][0]
    await register(db, tid, 2, entry_team_id=team["id"], entry_seat=1)
    t = await life.locked_event(db, tid)
    r = await api.own(db, t, await db.get(User, 2))
    r.seat_expires_at = life.now() - timedelta(seconds=1)
    await life.refresh_admissions(db, t)
    assert r.admission == "expired" and r.entry_team_id is None
    await register(db, tid, 3, entry_team_id=team["id"], entry_seat=1)
    single, _ = await event(db, 4)
    roster = (await api.get_tournament(single, None, db))["entry_teams"]
    assert len(roster) == 4 and all(len(t["seats"]) == 1 for t in roster)


@pytest.mark.asyncio
async def test_registration_reviews_expose_public_profile_and_level(db):
    user = await db.get(User, 2)
    user.ntrp_level, user.avatar_url = Decimal("3.5"), "https://example.test/avatar.jpg"
    tid, admin = await event(db, 4, TournamentConfig(approval_required=True))
    await register(db, tid, 2)
    r = (await api.get_tournament(tid, admin, db))["registrations"][0]
    assert r["user_ntrp_level"] == 3.5 and r["user_avatar"] == user.avatar_url
    db.add(Activity(id=90001, kind="post")); await db.flush()
    db.add(MatchPost(id=90001,user_id="1",title="等级展示")); await db.flush()
    db.add(MatchRegistration(post_id=90001,user_id="2",status="pending")); await db.flush()
    post = await posts.get_post(90001, db, admin)
    assert post.registrations[0].user_ntrp_level == Decimal("3.5")


@pytest.mark.asyncio
async def test_personal_organizer_contact_uses_activity_conversation(db, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(messages, "check_rate_limit", AsyncMock())
    tid, admin = await event(db, 4)
    t = await life.locked_event(db, tid)
    t.club_id, t.contact_phone = None, "13800000000"
    detail = await api.get_tournament(tid, None, db)
    assert detail["contact_phone"] is None and detail["organizer_user_id"] == admin.id
    c = await messages.contact(messages.ContactActivity(activity_id=tid), await db.get(User, 2), db)
    assert c["activity"] == {"id": tid, "kind": "tournament", "title": t.title}
    assert "phone" not in c["peer"]
    t.club_id = 1
    with pytest.raises(HTTPException) as error:
        await messages.contact(messages.ContactActivity(activity_id=tid), await db.get(User, 3), db)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_move_seat_preserves_former_partner_and_freezes_before_draw(db):
    tid, admin = await event(db, 4, TournamentConfig(discipline="doubles", pairing="fixed"))
    first, second = (await api.get_tournament(tid, None, db))["entry_teams"]
    await register(db, tid, 2, entry_team_id=first["id"], entry_seat=1)
    await register(db, tid, 3, entry_team_id=first["id"], entry_seat=2)
    user = await db.get(User, 2)
    await api.select_team_seat(tid, RegistrationCommand(entry_team_id=second["id"],entry_seat=1),user,db)
    t = await life.locked_event(db,tid)
    mate = await api.own(db,t,await db.get(User,3))
    assert mate.entry_team_id == first["id"] and mate.partner_user_id is None and mate.invite_token
    assert life.eligible(mate)
    await api.close_registration(tid,admin,db)
    with pytest.raises(HTTPException) as error:
        await api.select_team_seat(tid, RegistrationCommand(entry_team_id=first["id"],entry_seat=1),user,db)
    assert error.value.status_code == 409
