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
    db.add(ClubMember(club_id=1,user_id=2))
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
    assert not result.items[0]["can_manage"]

@pytest.mark.asyncio
async def test_cancel_with_legacy_paid_order_does_not_block_or_send_real_refund(db,monkeypatch):
    tid, admin = await event(db)
    await register(db,tid,2)
    from sqlalchemy import select
    reg = (await db.execute(select(TournamentRegistration).where(TournamentRegistration.tournament_id==tid))).scalar_one()
    order = BookingOrder(order_no="legacy-cancel",business_type="tournament",tournament_id=tid,club_id=1,user_id=2,amount=50,status=OrderStatus.paid,wx_transaction_id="dev_old")
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
