"""OpenID primary keys, real string references, authentication and snapshots."""
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tests.test_tournaments import db
from app.models.models import User, UserRole, ClubMember, MatchPost, MatchRegistration, Activity, Notification, NotificationType
from app.api.v1 import users, auth
from app.api.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token
from app.schemas.schemas import UserMeResponse, RefreshRequest


@pytest.mark.asyncio
async def test_openid_is_primary_key_and_all_personal_records_use_strings(db):
    player = User(openid='oWeChat_actual_primary_key', nickname='真实用户', role=UserRole.club_admin)
    other = User(openid='oWeChat_other_primary_key')
    db.add_all([player,other]); await db.flush()
    assert player.id == player.openid
    db.add(ClubMember(club_id=1,user_id=player.id))
    db.add(Activity(id=900,kind='post')); await db.flush()
    db.add(MatchPost(id=900,user_id=player.id,title='归属测试'))
    db.add(Notification(user_id=player.id,type=NotificationType.system,title='归属通知'))
    await db.commit()
    db.expunge_all()
    fresh = await db.get(User,'oWeChat_actual_primary_key')
    assert fresh.role == UserRole.club_admin
    me = await users.get_me(fresh,db)
    assert me.id == fresh.openid and me.managed_club_ids == [1]
    own_posts = await users.my_posts(page=1,page_size=20,current_user=fresh,db=db)
    assert len(own_posts.items) == 1 and own_posts.items[0].user_id == fresh.id
    assert (await users.my_posts(page=1,page_size=20,current_user=await db.get(User,other.id),db=db)).total == 0
    authenticated = await get_current_user('Bearer '+create_access_token(fresh.id),db)
    assert authenticated.id == fresh.id
    assert (await auth.refresh_token(RefreshRequest(refresh_token=create_refresh_token(fresh.id)),db)).access_token


@pytest.mark.asyncio
async def test_database_cannot_create_two_accounts_with_one_openid(db):
    db.add(User(openid='oWeChat_unique')); await db.commit()
    db.add(User(openid='oWeChat_unique'))
    with pytest.raises(IntegrityError): await db.flush()
    await db.rollback()


def test_snapshots_replace_only_user_identifiers():
    path=Path(__file__).parents[1]/'alembic/versions/20261008_user_openid.py'
    spec=importlib.util.spec_from_file_location('openid_migration',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source={'roster':[{'user_id':1,'partner_user_id':2,'requested_group':1}], 'users':[1,2], 'source_version':1,'team_id':2}
    value=module.remap_json(source,{'1':'openid-a','2':'openid-b'})
    assert value == {'roster':[{'user_id':'openid-a','partner_user_id':'openid-b','requested_group':1}], 'users':['openid-a','openid-b'], 'source_version':1,'team_id':2}
