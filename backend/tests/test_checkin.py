from datetime import timedelta
import pytest
from fastapi import HTTPException
from app.api.v1 import tournaments as api
from app.models.models import User, Tournament, TournamentRegistration
from app.schemas.tournament import RegistrationCommand, DrawCommand, DrawAdjustCommand
from app.services import tournament_lifecycle as life
from tests.test_tournaments import db, event

@pytest.mark.asyncio
async def test_checkin_permissions_window_idempotency_and_draw_gate(db, monkeypatch):
    tid, owner = await event(db, 2)
    regs = []
    for uid in ('2','3'):
        result = await api.register_tournament(tid, RegistrationCommand(), await db.get(User,uid), db)
        regs.append(await db.get(TournamentRegistration,result['registration_id']))
    t = await db.get(Tournament,tid)
    with pytest.raises(HTTPException) as e:
        await api.check_in(tid,regs[0].id,await db.get(User,'2'),db)
    assert e.value.status_code == 409
    monkeypatch.setattr(life,'now',lambda:t.start_time-timedelta(minutes=30))
    with pytest.raises(HTTPException) as e:
        await api.check_in(tid,regs[0].id,await db.get(User,'4'),db)
    assert e.value.status_code == 403
    await api.close_registration(tid,owner,db)
    with pytest.raises(HTTPException) as e:
        await api.create_draw(tid,DrawCommand(idempotency_key='attendance-gate'),owner,db)
    assert e.value.status_code == 409 and '签到' in e.value.detail
    first = await api.check_in(tid,regs[0].id,await db.get(User,'2'),db)
    assert await api.check_in(tid,regs[0].id,owner,db) == first
    assert regs[0].checked_in_by == '2'
    monkeypatch.setattr(life, 'now', lambda: t.end_time + timedelta(minutes=1))
    await api.check_in(tid,regs[1].id,owner,db)
    assert regs[1].checked_in_by == owner.id
    assert (await api.get_tournament(tid,owner,db))['unchecked_count'] == 0
    result = await api.create_draw(tid, DrawCommand(idempotency_key='attendance-gate'), owner, db)
    assert result['version'] == 1 and result['overflows']
    detail = await api.get_tournament(tid, owner, db)
    positions = detail['draw_positions']
    positions[0]['team_id'], positions[1]['team_id'] = positions[1]['team_id'], positions[0]['team_id']
    adjusted = await api.adjust_draw(tid, DrawAdjustCommand(expected_version=1,
        idempotency_key='late-adjustment', reason='晚到签到后调位', positions=positions), owner, db)
    assert adjusted['version'] == 2
    t.status='finished'
    with pytest.raises(HTTPException): await api.check_in(tid,regs[0].id,owner,db)

@pytest.mark.asyncio
async def test_overlap_warns_but_allows_registration_and_adjacent_is_clear(db):
    tid, owner=await event(db,2)
    other,_=await event(db,2)
    first=await db.get(Tournament,tid); second=await db.get(Tournament,other)
    second.start_time=first.start_time; second.end_time=first.end_time
    guest=await db.get(User,'2')
    await api.register_tournament(tid,RegistrationCommand(),guest,db)
    assert [r['id'] for r in await api.registration_conflicts(other,guest,db)]==[tid]
    await api.register_tournament(other,RegistrationCommand(),guest,db)
    second.start_time=first.end_time;second.end_time=first.end_time+timedelta(hours=1)
    assert await api.registration_conflicts(other,guest,db)==[]
