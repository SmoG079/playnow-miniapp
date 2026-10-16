"""Private text conversations, initiated through a public activity."""
import hashlib
import json
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import select,func,or_,case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.core.logger import get_logger
from app.models.models import User,MatchPost,Tournament,TournamentAudit,Activity,DirectConversation,DirectMessage
router=APIRouter(prefix='/messages',tags=['messages'])
logger=get_logger(__name__)

class ContactActivity(BaseModel):
    activity_id:int=Field(...,ge=1)

class SendMessage(BaseModel):
    client_id:str=Field(...,min_length=8,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    content:str=Field(...,min_length=1,max_length=2000)
    @field_validator('content')
    @classmethod
    def not_blank(cls,value):
        value=value.strip()
        if not value:raise ValueError('请输入消息内容')
        return value

class ReadMessages(BaseModel):
    through_id:int=Field(...,ge=0)

async def member(db,ident,user,lock=False):
    q=select(DirectConversation).where(DirectConversation.id==ident,or_(DirectConversation.participant_a==user.id,DirectConversation.participant_b==user.id))
    if lock:q=q.with_for_update().execution_options(populate_existing=True)
    c=await db.scalar(q)
    if not c:raise HTTPException(404,'会话不存在')
    return c

def unread_query(c,user):
    marker=c.read_a if c.participant_a==user.id else c.read_b
    return select(func.count()).select_from(DirectMessage).where(DirectMessage.conversation_id==c.id,DirectMessage.sender_id!=user.id,DirectMessage.id>marker)

async def conversation_data(db,c,user):
    peer=await db.get(User,c.participant_b if c.participant_a==user.id else c.participant_a)
    activity=await db.get(Activity,c.activity_id)
    item=await db.get(MatchPost if activity.kind=='post' else Tournament,c.activity_id)
    return dict(id=c.id,peer=dict(nickname=peer.nickname or '球友',avatar_url=peer.avatar_url),activity=dict(id=c.activity_id,kind=activity.kind,title=item.title),last_message=c.last_message_preview,last_message_at=c.last_message_at,unread_count=await db.scalar(unread_query(c,user)) or 0)

def message_data(m,user):
    return dict(id=m.id,client_id=m.client_id,content=m.content,is_mine=m.sender_id==user.id,created_at=m.created_at)

@router.post('/conversations')
async def contact(req:ContactActivity,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    activity=await db.get(Activity,req.activity_id)
    if not activity:raise HTTPException(404,'活动不存在')
    if activity.kind=='post':
        post=await db.get(MatchPost,activity.id)
        owner_id=post.user_id
    else:
        tournament=await db.get(Tournament,activity.id)
        if tournament.club_id:raise HTTPException(422,'俱乐部主办请使用赛事联系电话')
        owner_id=await db.scalar(select(TournamentAudit.actor_id).where(TournamentAudit.tournament_id==activity.id,TournamentAudit.action=='created').order_by(TournamentAudit.id).limit(1))
        if not owner_id:raise HTTPException(409,'主办方联系信息尚未设置')
    if owner_id==user.id:raise HTTPException(409,'不能给自己发私信')
    pair=sorted([user.id,owner_id])
    key=hashlib.sha256(json.dumps(pair,ensure_ascii=False).encode()).hexdigest()
    c=await db.scalar(select(DirectConversation).where(DirectConversation.pair_key==key))
    if not c:
        await check_rate_limit('message:contact:'+user.id,30,60)
        try:
            async with db.begin_nested():
                c=DirectConversation(pair_key=key,participant_a=pair[0],participant_b=pair[1],activity_id=activity.id)
                db.add(c);await db.flush()
        except IntegrityError:
            c=await db.scalar(select(DirectConversation).where(DirectConversation.pair_key==key).with_for_update())
            if not c:raise
    c=await member(db,c.id,user,True)
    c.activity_id=activity.id
    return await conversation_data(db,c,user)

@router.get('/conversations')
async def conversations(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=50),user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    peer=aliased(User)
    peer_id=case((DirectConversation.participant_a==user.id,DirectConversation.participant_b),else_=DirectConversation.participant_a)
    marker=case((DirectConversation.participant_a==user.id,DirectConversation.read_a),else_=DirectConversation.read_b)
    unread=select(func.count(DirectMessage.id)).where(DirectMessage.conversation_id==DirectConversation.id,DirectMessage.sender_id!=user.id,DirectMessage.id>marker).correlate(DirectConversation).scalar_subquery()
    q=select(DirectConversation,peer.nickname,peer.avatar_url,Activity.kind,MatchPost.title,Tournament.title,unread).join(peer,peer.id==peer_id).join(Activity,Activity.id==DirectConversation.activity_id).outerjoin(MatchPost,MatchPost.id==Activity.id).outerjoin(Tournament,Tournament.id==Activity.id).where(or_(DirectConversation.participant_a==user.id,DirectConversation.participant_b==user.id),DirectConversation.last_message_id.is_not(None))
    total=await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows=(await db.execute(q.order_by(DirectConversation.last_message_at.desc(),DirectConversation.id).offset((page-1)*page_size).limit(page_size))).all()
    items=[dict(id=c.id,peer=dict(nickname=nick or '球友',avatar_url=avatar),activity=dict(id=c.activity_id,kind=kind,title=post_title if kind=='post' else tournament_title),last_message=c.last_message_preview,last_message_at=c.last_message_at,unread_count=count or 0) for c,nick,avatar,kind,post_title,tournament_title,count in rows]
    return dict(items=items,total=total,page=page,page_size=page_size)

@router.get('/unread-count')
async def unread_count(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    marker=case((DirectConversation.participant_a==user.id,DirectConversation.read_a),else_=DirectConversation.read_b)
    count=await db.scalar(select(func.count(DirectMessage.id)).join(DirectConversation,DirectMessage.conversation_id==DirectConversation.id).where(or_(DirectConversation.participant_a==user.id,DirectConversation.participant_b==user.id),DirectMessage.sender_id!=user.id,DirectMessage.id>marker)) or 0
    return dict(count=count)

@router.get('/conversations/{ident}')
async def detail(ident:str,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    return await conversation_data(db,await member(db,ident,user),user)

@router.get('/conversations/{ident}/messages')
async def history(ident:str,before_id:int|None=Query(None,ge=1),after_id:int|None=Query(None,ge=0),page_size:int=Query(30,ge=1,le=50),user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    await member(db,ident,user)
    if before_id is not None and after_id is not None:raise HTTPException(422,'历史与新消息游标不能同时填写')
    q=select(DirectMessage).where(DirectMessage.conversation_id==ident)
    if before_id is not None:q=q.where(DirectMessage.id<before_id)
    if after_id is not None:q=q.where(DirectMessage.id>after_id)
    q=q.order_by(DirectMessage.id.asc() if after_id is not None else DirectMessage.id.desc())
    rows=list((await db.scalars(q.limit(page_size+1))).all());more=len(rows)>page_size;rows=rows[:page_size]
    if after_id is None:rows.reverse()
    return dict(items=[message_data(m,user) for m in rows],has_more=more)

@router.post('/conversations/{ident}/messages')
async def send(ident:str,req:SendMessage,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    c=await member(db,ident,user,True)
    existing=await db.scalar(select(DirectMessage).where(DirectMessage.conversation_id==ident,DirectMessage.sender_id==user.id,DirectMessage.client_id==req.client_id).with_for_update())
    if existing:
        if existing.content!=req.content:raise HTTPException(409,'消息重试内容已变化')
        return message_data(existing,user)
    await check_rate_limit('message:send:'+user.id,30,60)
    m=DirectMessage(conversation_id=ident,sender_id=user.id,client_id=req.client_id,content=req.content)
    db.add(m);await db.flush()
    c.last_message_id=m.id;c.last_message_preview=req.content[:200];c.last_message_at=m.created_at
    logger.info('Direct message created: conversation=%s message=%s',ident,m.id)
    return message_data(m,user)

@router.post('/conversations/{ident}/read')
async def mark_read(ident:str,req:ReadMessages,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    c=await member(db,ident,user,True)
    through=min(req.through_id,c.last_message_id or 0)
    if user.id==c.participant_a:c.read_a=max(c.read_a,through)
    else:c.read_b=max(c.read_b,through)
    return dict(unread_count=await db.scalar(unread_query(c,user)) or 0)
