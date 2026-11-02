"""Only authenticated activity owners can inspect or withdraw their receipts."""
import json
import time
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.core.wechat_pay import get_wxpay
from app.models.models import User, ActivityWithdrawal, ActivityTransfer
from app.services import activity_wallet as wallet

router = APIRouter(prefix='/activity-wallet', tags=['activity-wallet'])


class WithdrawalRequest(BaseModel):
    request_key: str = Field(min_length=8,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    activity_ids: list[int] = Field(default_factory=list,max_length=100)


@router.get('')
async def overview(start: date | None = None, end: date | None = None, club_id: int | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if start and end and start > end: raise HTTPException(422,'开始日期不能晚于结束日期')
    return await wallet.overview(db,user.id,start,end,club_id)


@router.post('/withdrawals')
async def withdraw(req: WithdrawalRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await check_rate_limit('rate:withdraw:'+user.id,max_requests=10,window_seconds=60)
    record = await wallet.reserve(db,user,req.request_key,req.activity_ids)
    bills = (await db.scalars(select(ActivityTransfer).where(ActivityTransfer.withdrawal_id == record.id).order_by(ActivityTransfer.id))).all()
    await db.commit()
    return {'id':record.id,'amount_cents':sum(b.amount_cents for b in bills),'bills':[{'id':b.id,'amount_cents':b.amount_cents,'state':b.state} for b in bills]}


@router.post('/transfers/{bill_id}/sync')
async def sync(bill_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await check_rate_limit('rate:withdraw-sync:'+user.id,max_requests=30,window_seconds=60)
    bill = await wallet.sync_bill(db,user.id,bill_id)
    result = {'id':bill.id,'state':bill.state,'amount_cents':bill.amount_cents}
    if bill.state == 'WAIT_USER_CONFIRM' and bill.package_info:
        result['confirmation'] = dict(mchId=bill.request_payload['_mchid'],appId=bill.request_payload['appid'],package=bill.package_info)
    return result


@router.post('/notify')
async def notify(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        timestamp = int(request.headers.get('Wechatpay-Timestamp','0'))
        if abs(time.time()-timestamp) > 300 or not request.headers.get('Wechatpay-Nonce'): raise ValueError()
        body = await request.body()
        data = json.loads(get_wxpay().decrypt_callback(dict(request.headers),body))
    except Exception:
        raise HTTPException(400,'Invalid transfer notification')
    row = (await db.execute(select(ActivityTransfer.id,ActivityWithdrawal.owner_id).join(ActivityWithdrawal).where(ActivityTransfer.out_bill_no == data.get('out_bill_no')))).first()
    if not row: raise HTTPException(404,'Transfer not found')
    await db.scalar(select(User).where(User.id == row.owner_id).with_for_update())
    bill = await db.scalar(select(ActivityTransfer).where(ActivityTransfer.id == row.id).with_for_update().execution_options(populate_existing=True))
    wallet.apply_result(bill,data)
    await db.commit()
    return {'code':'SUCCESS'}
