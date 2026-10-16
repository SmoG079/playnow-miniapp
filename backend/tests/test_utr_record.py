"""Real authentication and role boundaries for the UTR preview; no fake results."""
from decimal import Decimal
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from app.api.v1 import users
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.models import User, UserRole, UserUtrRecord
from tests.test_post_booking_permissions import db


@pytest.mark.asyncio
async def test_utr_record_requires_authenticated_platform_admin(db):
    app = FastAPI(); app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: db
    admin = await db.get(User, '1')
    admin.role = UserRole.platform_admin
    admin.utr_rating = Decimal('3.40'); admin.ntrp_level = Decimal('5.0')
    await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://isolated') as client:
        assert (await client.get('/users/me/utr-record')).status_code == 401
        assert (await client.get('/users/me/utr-record', headers={'Authorization':'Bearer invalid'})).status_code == 401
        normal = {'Authorization':'Bearer '+create_access_token('2')}
        assert (await client.get('/users/me/utr-record', headers=normal)).status_code == 403
        guest = await db.get(User, '2'); guest.role = UserRole.club_admin; await db.commit()
        assert (await client.get('/users/me/utr-record', headers=normal)).status_code == 403
        headers = {'Authorization':'Bearer '+create_access_token('1')}
        response = await client.get('/users/me/utr-record', headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['rating'] == 3.4 and data['ntrp_level'] == 5.0
        assert all(data[key] is None for key in ('matches_played','wins','losses','world_rank','age_group'))
        assert 'phone' not in data and 'openid' not in data
        # Changing the stored role revokes access even with the same valid token.
        admin.role = UserRole.user; await db.commit()
        assert (await client.get('/users/me/utr-record', headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_no_database_rating_is_presented_as_zero_or_derived_from_ntrp(db):
    app = FastAPI(); app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: db
    admin = await db.get(User, '1'); admin.role = UserRole.platform_admin
    admin.utr_rating = None; admin.ntrp_level = Decimal('4.5'); await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://isolated') as client:
        response = await client.get('/users/me/utr-record', headers={'Authorization':'Bearer '+create_access_token('1')})
    assert response.status_code == 200
    assert response.json()['rating'] is None
    assert response.json()['ntrp_level'] == 4.5


@pytest.mark.asyncio
async def test_stored_official_statistics_preserve_real_zero_and_null(db):
    app = FastAPI(); app.include_router(users.router)
    app.dependency_overrides[get_db] = lambda: db
    admin = await db.get(User, '1'); admin.role = UserRole.platform_admin
    admin.utr_rating = Decimal('3.40')
    stats = UserUtrRecord(user_id='1', matches_played=1, wins=0, losses=1, world_rank=329791, age_group='22–29')
    db.add(stats); await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://isolated') as client:
        headers = {'Authorization':'Bearer '+create_access_token('1')}
        data = (await client.get('/users/me/utr-record', headers=headers)).json()
        assert {key:data[key] for key in ('rating','matches_played','wins','losses','world_rank','age_group')} == dict(rating=3.4,matches_played=1,wins=0,losses=1,world_rank=329791,age_group='22–29')
        stats.wins = None; stats.world_rank = None; await db.commit()
        data = (await client.get('/users/me/utr-record', headers=headers)).json()
        assert data['wins'] is None and data['world_rank'] is None
        assert data['matches_played'] == 1


@pytest.mark.asyncio
async def test_source_payload_import_reuses_wechat_primary_key_and_preserves_ntrp(db):
    from sqlalchemy import select, func
    from app.services.utr_records import import_utr_snapshot
    user = await db.get(User, '1'); original_ntrp = user.ntrp_level
    payload = {'label':'Ages 30 & Over','lose':'0','played':'1','rank':'121029','rating':'3.59','won':'1'}
    row = await import_utr_snapshot(db, user.id, payload); await db.commit()
    assert row.user_id == user.id
    assert user.utr_rating == Decimal('3.59') and user.ntrp_level == original_ntrp
    assert (row.matches_played,row.wins,row.losses,row.world_rank,row.age_group) == (1,1,0,121029,'Ages 30 & Over')
    # Re-importing updates the same primary key, without adding a second record.
    payload['rating'] = '3.60'; payload['rank'] = '120000'
    row2 = await import_utr_snapshot(db, user.id, payload); await db.commit()
    assert row2.user_id == row.user_id and user.utr_rating == Decimal('3.60') and row2.world_rank == 120000
    assert await db.scalar(select(func.count()).select_from(UserUtrRecord).where(UserUtrRecord.user_id == user.id)) == 1
    # An explicitly empty full snapshot stays empty, rather than inventing zero.
    await import_utr_snapshot(db, user.id, dict.fromkeys(payload)); await db.commit()
    assert user.utr_rating is None and row2.world_rank is None and row2.losses is None
    assert user.ntrp_level == original_ntrp


def test_invalid_source_payloads_cannot_silently_replace_values():
    from app.services.utr_records import parse_utr_snapshot
    payload = {'label':'Ages 30 & Over','lose':'0','played':'1','rank':'121029','rating':'3.59','won':'1'}
    for field,value in [('played','1.5'),('won',True),('lose','-1'),('rank','0'),('rating','NaN'),('rating','3.591'),('label','x'*33)]:
        with pytest.raises(ValueError): parse_utr_snapshot(dict(payload,**{field:value}))
    with pytest.raises(ValueError): parse_utr_snapshot({'rating':'3.59'})
    empty = parse_utr_snapshot(dict.fromkeys(payload,''))
    assert empty.rating is None and empty.wins is None and empty.age_group is None
