from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.api.v1 import clubs
from app.api.deps import get_club_admin
from app.core.database import get_db
from app.models.models import (
    Club, User, ClubMember, CommunityMember, MatchPost, MatchRegistration, RegistrationStatus,
    TournamentRegistration, TournamentRegStatus,
)
from tests.test_discovery import post
from tests.test_tournaments import db, event

@pytest.mark.asyncio
async def test_membership_is_idempotent_and_never_grants_management(db):
    owner, guest = await db.get(User, '1'), await db.get(User, '2')
    club = await db.get(Club, 1)
    club.created_by = owner.id
    await db.flush()
    await clubs.join_community(1, guest, db)
    await clubs.join_community(1, guest, db)
    state = await clubs.community_state(1, db, guest)
    assert state['count'] == 1 and state['joined'] and not state['owner']
    assert state['members'] == []
    assert not await db.scalar(select(ClubMember.id).where(ClubMember.user_id == guest.id))
    with pytest.raises(HTTPException) as e: await get_club_admin(1, guest, db)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException): await clubs.remove_community_member(1, guest.public_id, guest, db)
    await clubs.remove_community_member(1, guest.public_id, owner, db)
    assert not (await clubs.community_state(1, db, guest))['joined']
    await clubs.join_community(1, guest, db)
    await clubs.leave_community(1, guest, db)
    await clubs.leave_community(1, guest, db)
    with pytest.raises(HTTPException): await clubs.leave_community(1, owner, db)


@pytest.mark.asyncio
async def test_public_club_members_show_paginated_profiles_and_confirmed_activity_counts(db):
    tournament_id, owner = await event(db)
    club = await db.get(Club, 1)
    club.created_by = owner.id
    guest = await db.get(User, "3")
    guest.avatar_url = "https://example.com/avatar.png"
    first = await post(db, "扬州市", "2030-01-01")
    second = await post(db, "扬州市", "2030-01-02")
    (await db.get(MatchPost, first.id)).club_id = 1
    (await db.get(MatchPost, second.id)).club_id = 2
    joined_at = datetime(2026, 11, 7, 17)
    db.add_all([
        CommunityMember(club_id=1, user_id=guest.id, created_at=joined_at),
        CommunityMember(club_id=1, user_id=owner.id, created_at=joined_at),
        MatchRegistration(post_id=first.id, user_id=guest.id, status=RegistrationStatus.approved),
        MatchRegistration(post_id=second.id, user_id=guest.id, status=RegistrationStatus.approved),
        TournamentRegistration(tournament_id=tournament_id, user_id=guest.id,
                               status=TournamentRegStatus.confirmed),
        TournamentRegistration(tournament_id=tournament_id, user_id=owner.id,
                               status=TournamentRegStatus.cancelled),
    ])
    await db.flush()

    app = FastAPI()
    app.include_router(clubs.router)

    async def isolated_db():
        yield db

    app.dependency_overrides[get_db] = isolated_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://isolated") as client:
        response = await client.get("/clubs/1/members?page_size=1")
        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert response.json()["items"] == [{
            "id": guest.public_id, "name": guest.nickname, "avatar_url": guest.avatar_url,
            "joined_date": "2026-11-08", "activity_count": 2, "is_owner": False,
        }]
        response = await client.get("/clubs/1/members?page_size=1&page=2")
        assert response.status_code == 200
        member, = response.json()["items"]
        assert member["id"] == owner.public_id and member["is_owner"] and member["activity_count"] == 0
        club.approval_status = "pending"
        assert (await client.get("/clubs/1/members")).status_code == 404


@pytest.mark.asyncio
async def test_unapproved_club_cannot_be_joined(db):
    club = await db.get(Club, 1)
    club.approval_status = 'pending'
    with pytest.raises(HTTPException) as e: await clubs.join_community(1, await db.get(User, '2'), db)
    assert e.value.status_code == 404
    assert not (await db.scalars(select(CommunityMember))).all()

@pytest.mark.asyncio
async def test_city_discovery_includes_clubs_without_courts(db):
    club = await db.get(Club, 1)
    club.city = "上海市"
    await db.flush()
    result = await clubs.list_clubs(community=True, city="上海市", lat=None, lng=None, sport=None, keyword=None, page=1, page_size=20, db=db)
    assert result.total == 1 and result.items[0].id == club.id

@pytest.mark.asyncio
async def test_member_count_matches_state_in_detail_and_listing(db):
    await clubs.join_community(1, await db.get(User, '2'), db)
    assert (await clubs.get_club(1, db, None)).member_count == 1
    for community in (False, True):
        result = await clubs.list_clubs(community=community, city=None, lat=None, lng=None, sport=None, keyword=None, page=1, page_size=20, db=db)
        assert next(c for c in result.items if c.id == 1).member_count == 1


@pytest.mark.asyncio
async def test_club_activity_history_is_scoped_and_filters_finished_events(db):
    from app.models.models import Tournament

    upcoming, _ = await event(db)
    ended, _ = await event(db)
    unrelated, _ = await event(db)
    (await db.get(Tournament, ended)).status = "finished"
    (await db.get(Tournament, unrelated)).club_id = 2
    await db.flush()
    all_activities = await clubs.club_activities(1, page=1, page_size=20, db=db)
    assert all_activities["total"] == 2
    assert {row["id"] for row in all_activities["items"]} == {upcoming, ended}
    history = await clubs.club_activities(1, "ended", page=1, page_size=20, db=db)
    assert [(row["id"], row["phase"]) for row in history["items"]] == [(ended, "ended")]
