"""Required create fields, managed lists and cancellation persistence."""
import pytest
from pydantic import ValidationError
from app.api.v1 import users, posts, tournaments
from app.models.models import User, UserRole, ClubMember, MatchPost, BookingOrder, OrderStatus, TournamentRegistration
from app.schemas.schemas import PostCreate
from app.schemas.tournament import TournamentCreate, ReasonCommand
from tests.test_tournaments import db, event, register

POST = dict(title="约球", preferred_date="2026-11-01", preferred_start="09:00", preferred_end="11:00", players_needed=2, price=0)
TOURNAMENT = dict(title="比赛", club_id=1, address="网球公园", max_participants=8, start_time="2026-11-01T09:00:00+08:00", end_time="2026-11-01T17:00:00+08:00")


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"preferred_start": "12:00"}, {"preferred_end": "08:00"},
    {"preferred_start": "12:00", "preferred_end": "11:00"},
    {"latitude": 32.4},
])
async def test_post_partial_edits_validate_merged_time_and_coordinates(db, payload):
    from fastapi import HTTPException
    from app.schemas.schemas import PostUpdate
    owner = await db.get(User, 2)
    post = await posts.create_post(PostCreate(**POST), owner, db)
    with pytest.raises(HTTPException) as exc:
        await posts.update_post(post.id, PostUpdate(**payload), owner, db)
    assert exc.value.status_code == 422
    updated = await posts.update_post(post.id, PostUpdate(preferred_end="12:00"), owner, db)
    assert updated.preferred_end.hour == 12


@pytest.mark.parametrize("payload", [{"price": -1}, {"status": "invalid"}, {"status": None}, {"title": "x" * 257}])
def test_invalid_post_edits_are_rejected_before_database(payload):
    from app.schemas.schemas import PostUpdate
    with pytest.raises(ValidationError):
        PostUpdate(**payload)


@pytest.mark.asyncio
async def test_comment_total_covers_all_pages_without_counting_replies(db):
    from app.models.models import Comment
    from datetime import datetime
    owner = await db.get(User, 2)
    post = await posts.create_post(PostCreate(**POST), owner, db)
    comments = [Comment(post_id=post.id, user_id=owner.id, content=f"评论{i}",
                        created_at=datetime(2026, 10, 8)) for i in range(23)]
    db.add_all(comments)
    await db.flush()
    db.add(Comment(post_id=post.id, user_id=owner.id, content="回复", parent_id=comments[0].id))
    first = await posts.list_comments(post.id, 1, 20, db)
    second = await posts.list_comments(post.id, 2, 20, db)
    assert first.total == second.total == 23
    assert len(first.items) == 20 and len(second.items) == 3
    assert len({c.id for c in first.items + second.items}) == 23

@pytest.mark.parametrize("schema,data,field", [(PostCreate,POST,f) for f in ("title","preferred_date","preferred_start","preferred_end","players_needed")]+[(TournamentCreate,TOURNAMENT,f) for f in ("title","start_time","end_time","max_participants","address")])
@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_null_required_fields_rejected_before_database(schema, data, field, missing):
    payload = dict(data)
    if missing: payload.pop(field)
    else: payload[field] = None
    with pytest.raises(ValidationError): schema.model_validate(payload)

@pytest.mark.parametrize("schema,data,field", [(PostCreate,POST,"title"),(TournamentCreate,TOURNAMENT,"title"),(TournamentCreate,TOURNAMENT,"address")])
def test_whitespace_required_text_rejected(schema,data,field):
    with pytest.raises(ValidationError): schema.model_validate(dict(data, **{field:"   "}))

@pytest.mark.asyncio
async def test_management_list_includes_created_and_closed_events_and_is_scoped(db):
    tid, admin = await event(db)
    creator = await db.get(User, 2)
    creator.role = UserRole.club_admin
    db.add(ClubMember(club_id=1,user_id='2'))
    await db.flush()
    created = await tournaments.create_tournament(TournamentCreate(**TOURNAMENT),creator,db)
    result = await users.managed_tournaments(1,20,creator,db)
    assert {x["id"] for x in result.items} == {tid,created["id"]}
    await tournaments.cancel_event(created["id"],ReasonCommand(reason="取消测试"),creator,db)
    result = await users.managed_tournaments(1,20,creator,db)
    assert next(x for x in result.items if x["id"]==created["id"])["status"]=="cancelled"
    assert (await users.managed_tournaments(1,20,await db.get(User,3),db)).total==0
    creator.role = UserRole.user
    result = await users.managed_tournaments(1,20,creator,db)
    assert [x["id"] for x in result.items]==[created["id"]]
    assert result.items[0]["can_manage"]

@pytest.mark.asyncio
async def test_cancel_with_legacy_paid_order_does_not_block_or_send_real_refund(db,monkeypatch):
    tid, admin = await event(db)
    await register(db,tid,2)
    from sqlalchemy import select
    reg = (await db.execute(select(TournamentRegistration).where(TournamentRegistration.tournament_id==tid))).scalar_one()
    order = BookingOrder(order_no="legacy-cancel",business_type="tournament",tournament_id=tid,club_id=1,user_id='2',amount=50,status=OrderStatus.paid,wx_transaction_id="dev_old")
    db.add(order); await db.flush(); reg.order_id=order.id
    from app.services import tournament_lifecycle as life
    async def forbidden(*args): raise AssertionError("Legacy payment cannot request real refund")
    monkeypatch.setattr(life,"request_refund",forbidden)
    await tournaments.cancel_event(tid,ReasonCommand(reason="关闭测试"),admin,db)
    await db.commit()
    detail=await tournaments.get_tournament(tid,admin,db)
    assert detail["status"]=="cancelled" and detail["current_participants"]==0
    assert reg.admission=="cancelled" and reg.payment=="unverified" and order.refund_status=="abnormal" and order.status==OrderStatus.paid
    await tournaments.cancel_event(tid,ReasonCommand(reason="重复关闭"),admin,db)

@pytest.mark.asyncio
async def test_closing_post_preserves_signup_history(db):
    owner=await db.get(User,2)
    post=await posts.create_post(PostCreate(**POST),owner,db)
    from app.schemas.schemas import RegisterPostRequest
    await posts.register_post(post.id,RegisterPostRequest(),await db.get(User,3),db)
    await posts.close_post(post.id,owner,db)
    await db.commit()
    assert (await users.my_post_registrations(1,20,await db.get(User,3),db)).total==1
    assert (await db.get(MatchPost,post.id)).status.value=="closed"

@pytest.mark.asyncio
async def test_regular_creator_can_manage_draw_results_and_cancel_but_other_user_cannot(db):
    from fastapi import HTTPException
    from app.schemas.tournament import TournamentConfig, DrawCommand, VersionCommand, ResultCommand
    owner=await db.get(User,2)
    other=await db.get(User,5)
    req=TournamentCreate(**dict(TOURNAMENT,max_participants=2,config=TournamentConfig()))
    created=await tournaments.create_tournament(req,owner,db)
    tid=created['id']
    await db.commit()
    assert (await tournaments.get_tournament(tid,owner,db))['can_manage']
    assert not (await tournaments.get_tournament(tid,other,db))['can_manage']
    assert (await users.managed_tournaments(1,20,owner,db)).items[0]['can_manage']
    for action in (
        lambda: tournaments.update_tournament(tid,req,other,db),
        lambda: tournaments.close_registration(tid,other,db),
        lambda: tournaments.create_draw(tid,DrawCommand(idempotency_key='other-user-draw'),other,db),
        lambda: tournaments.cancel_event(tid,ReasonCommand(reason='无权限取消'),other,db),
    ):
        with pytest.raises(HTTPException) as err: await action()
        assert err.value.status_code==403
    await tournaments.update_tournament(tid,req,owner,db)
    for uid in (3,4): await register(db,tid,uid)
    await tournaments.close_registration(tid,owner,db)
    await tournaments.create_draw(tid,DrawCommand(idempotency_key='regular-creator-draw'),owner,db)
    await tournaments.publish_draw(tid,VersionCommand(expected_version=1),owner,db)
    match=(await tournaments.get_tournament(tid,owner,db))['matches'][0]
    await tournaments.record_result(tid,match['id'],ResultCommand(expected_version=1,winner_id=match['team_a_id'],score='6:4'),owner,db)
    assert (await tournaments.get_tournament(tid,None,db))['matches'][0]['score']=='6:4'
    await tournaments.cancel_event(tid,ReasonCommand(reason='创建者取消'),owner,db)
    assert (await tournaments.get_tournament(tid,owner,db))['status']=='cancelled'

@pytest.mark.asyncio
async def test_unknown_host_club_is_rejected_for_all_creators(db):
    from fastapi import HTTPException
    req=TournamentCreate(**dict(TOURNAMENT,club_id=999,config={}))
    for action in (tournaments.preview,tournaments.create_tournament):
        with pytest.raises(HTTPException) as err: await action(req,await db.get(User,2),db)
        assert err.value.status_code==422

@pytest.mark.asyncio
@pytest.mark.parametrize('levels,status', [(None,None),('3.0',None),(None,'closed'),('3.0','closed'),(None,'full')])
async def test_closed_posts_hidden_in_public_square_and_filters_but_history_retained(db,levels,status):
    owner=await db.get(User,2)
    public=await posts.create_post(PostCreate(**dict(POST,city="扬州市",level_required='3.0')),owner,db)
    closed=await posts.create_post(PostCreate(**dict(POST,city='扬州市',title='已关闭活动',level_required='3.0')),owner,db)
    from app.models.models import MatchPostStatus
    (await db.get(MatchPost,public.id)).status=MatchPostStatus.full
    await posts.close_post(closed.id,owner,db)
    await db.commit()
    listing=await posts.list_posts(city="扬州市",club_id=None,sport=None,status=status,ntrp_levels=levels,
        lat=None,lng=None,sort_by='created',page=1,page_size=20,db=db)
    expected=[] if status=='closed' else [public.id]
    assert [x.id for x in listing.items]==expected
    assert listing.total==len(expected)
    history=await users.my_posts(1,20,owner,db)
    assert closed.id in [x.id for x in history.items]

@pytest.mark.asyncio
async def test_review_and_cancellation_cannot_reopen_closed_post(db):
    from fastapi import HTTPException
    from app.schemas.schemas import RegisterPostRequest, ReviewRegistrationRequest
    owner=await db.get(User,2)
    participant=await db.get(User,3)
    post=await posts.create_post(PostCreate(**dict(POST,players_needed=1)),owner,db)
    await posts.register_post(post.id,RegisterPostRequest(),participant,db)
    await posts.close_post(post.id,owner,db)
    with pytest.raises(HTTPException) as err:
        await posts.review_registration(post.id,participant.id,ReviewRegistrationRequest(status='approved'),owner,db)
    assert err.value.status_code==409
    await posts.cancel_register(post.id,participant,db)
    assert (await db.get(MatchPost,post.id)).status.value=='closed'
