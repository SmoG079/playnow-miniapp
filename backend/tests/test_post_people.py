from datetime import date, timedelta
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.v1 import posts, tournaments
from app.core.database import get_db
from app.models.models import MatchPost, User, UserRole
from app.schemas.schemas import PostCreate, PostUpdate, RegisterPostRequest
from tests.test_post_booking_permissions import db  # noqa: F401


def payload(**extra):
    return dict(title="周末约球", preferred_date=date.today()+timedelta(days=10),
        preferred_start="09:00", preferred_end="11:00", city="扬州市", price=0, **extra)


def test_people_validation():
    assert PostCreate(**payload(max_players=4)).min_players == 2
    assert PostCreate(**payload(max_players=4, min_players=3)).max_players == 4
    assert PostUpdate(max_players=4).model_dump(exclude_unset=True)["max_players"] == 4
    for invalid in [dict(min_players=4,max_players=3),dict(min_players=1,max_players=4),dict(max_players=1)]:
        with pytest.raises(ValidationError): PostCreate(**payload(**invalid))
    for invalid in [dict(min_players=None),dict(max_players=None),dict(min_players=4,max_players=3)]:
        with pytest.raises(ValidationError): PostUpdate(**invalid)


@pytest.mark.asyncio
async def test_persist_and_update_total_people(db):
    owner=await db.get(User,"1")
    result=await posts.create_post(PostCreate(**payload(min_players=3,max_players=4)), owner, db)
    assert (result.min_players,result.max_players)==(3,4)
    stored=await db.get(MatchPost,result.id)
    assert stored.min_players==3
    with pytest.raises(HTTPException) as exc:
        await posts.update_post(result.id,PostUpdate(max_players=2),owner,db)
    assert exc.value.status_code==422
    updated=await posts.update_post(result.id,PostUpdate(min_players=2,max_players=2),owner,db)
    assert (updated.min_players,updated.max_players)==(2,2)


@pytest.mark.asyncio
async def test_organizer_counts_once_and_maximum_stops_registration(db):
    owner,guest=await db.get(User,"1"),await db.get(User,"2")
    result=await posts.create_post(PostCreate(**payload(max_players=2)),owner,db)
    with pytest.raises(HTTPException) as exc:
        await posts.register_post(result.id,RegisterPostRequest(),owner,db)
    assert exc.value.status_code==409
    await posts.register_post(result.id,RegisterPostRequest(),guest,db)
    await db.flush()
    stored=await db.get(MatchPost,result.id)
    assert stored.status.value=="full"
    extra=User(id="3",openid="third",role=UserRole.user)
    db.add(extra);await db.flush()
    with pytest.raises(HTTPException):
        await posts.register_post(result.id,RegisterPostRequest(),extra,db)


def test_both_registration_routes_require_valid_access_token():
    from app.core.security import create_access_token, create_refresh_token
    app=FastAPI();app.include_router(posts.router);app.include_router(tournaments.router)
    database=AsyncMock()
    async def isolated_db(): yield database
    app.dependency_overrides[get_db]=isolated_db
    client=TestClient(app)
    for path in ("/posts/1/register","/tournaments/1/register"):
        for token in (None,"invalid",create_refresh_token("1"),create_access_token("1",timedelta(seconds=-60))):
            response=client.post(path,json={},headers={"Authorization":"Bearer "+token} if token else {})
            assert response.status_code==401
    database.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_cannot_shrink_below_confirmed_people(db):
    owner,guest=await db.get(User,"1"),await db.get(User,"2")
    extra=User(id="3",openid="third",role=UserRole.user)
    db.add(extra);await db.flush()
    result=await posts.create_post(PostCreate(**payload(min_players=2,max_players=3)),owner,db)
    await posts.register_post(result.id,RegisterPostRequest(),guest,db)
    await db.flush()
    await posts.register_post(result.id,RegisterPostRequest(),extra,db)
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await posts.update_post(result.id,PostUpdate(max_players=2),owner,db)
    assert exc.value.status_code==422
