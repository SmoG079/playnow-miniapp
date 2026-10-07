"""Exercise guarded destructive cleanup only on disposable MySQL."""
import importlib.util
import os
from pathlib import Path
import secrets
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from datetime import datetime,timedelta
from app.models.models import Activity,MatchPost,Tournament,User,Club,BookingOrder,OrderStatus
URL=os.environ.get('ACTIVITY_MYSQL_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Isolated MySQL required')
spec=importlib.util.spec_from_file_location('activity_cleanup',Path(__file__).resolve().parents[1]/'scripts/cleanup_incomplete_activities.py')
cleanup_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup_module)

def test_cleanup_keeps_valid_records_financial_orders_and_global_numbers():
    url=make_url(URL)
    assert url.database=='test_db' or url.database.startswith(('playnow_test_','playnow_migration_'))
    engine=sa.create_engine(url.set(drivername='mysql+pymysql'),poolclass=sa.pool.NullPool)
    ids=[];uid=cid=oid=None
    try:
        with Session(engine) as db:
            u=User(openid='cleanup-'+secrets.token_hex(8));c=Club(name='清理测试');db.add_all([u,c]);db.flush();uid,cid=u.id,c.id
            for kind in ('post','post','tournament','tournament'):
                a=Activity(kind=kind);db.add(a);db.flush();ids.append(a.id)
            db.add(MatchPost(id=ids[0],user_id=uid,title='缺时间',players_needed=2,price=0))
            db.add(MatchPost(id=ids[1],user_id=uid,title='完整',players_needed=2,price=0,preferred_date=datetime.utcnow().date(),preferred_start=datetime.strptime('09:00','%H:%M').time(),preferred_end=datetime.strptime('11:00','%H:%M').time()))
            for ident in ids[2:]: db.add(Tournament(id=ident,club_id=cid,title='缺地点',start_time=datetime.utcnow(),end_time=datetime.utcnow()+timedelta(hours=1),max_participants=8))
            db.flush()
            order=BookingOrder(order_no='cleanup-'+secrets.token_hex(8),user_id=uid,club_id=cid,tournament_id=ids[3],business_type='tournament',amount=0,status=OrderStatus.pending)
            db.add(order);db.flush();oid=order.id;db.commit()
        with engine.begin() as c:
            review=cleanup_module.plan(c)
            assert ids[0] in review['post_ids'] and ids[1] not in review['post_ids']
            assert ids[2] in review['tournament_ids'] and ids[3] in review['blocked_tournament_ids']
            with pytest.raises(RuntimeError): cleanup_module.cleanup(c,'outdated')
            cleanup_module.cleanup(c,review['fingerprint'])
        with Session(engine) as db:
            assert db.get(MatchPost,ids[0]) is None and db.get(Tournament,ids[2]) is None
            assert db.get(MatchPost,ids[1]) and db.get(Tournament,ids[3]) and db.get(BookingOrder,oid)
            assert all(db.get(Activity,i) for i in ids)
    finally:
        with engine.begin() as c:
            if oid: c.execute(sa.delete(BookingOrder).where(BookingOrder.id==oid))
            if ids:
                c.execute(sa.delete(MatchPost).where(MatchPost.id.in_(ids)));c.execute(sa.delete(Tournament).where(Tournament.id.in_(ids)));c.execute(sa.delete(Activity).where(Activity.id.in_(ids)))
            if uid: c.execute(sa.delete(User).where(User.id==uid))
            if cid: c.execute(sa.delete(Club).where(Club.id==cid))
        engine.dispose()
