import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.api.v1 import clubs
from app.api.deps import get_club_admin
from app.models.models import Club, User, ClubMember, CommunityMember
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
