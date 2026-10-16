"""Sort and paginate both activity kinds together before loading card data."""
from datetime import datetime, timedelta
from sqlalchemy import select, func, case, literal, text, cast, String
from app.models.models import (MatchPost, Tournament, Venue, User, MatchRegistration,
    RegistrationStatus, TournamentRegistration, TournamentRegStatus)
from app.services.discovery import city_name, ordered
from app.services.activity_visibility import public_listing_condition
from app.api.v1 import posts, tournaments


async def load_card_participants(db, cards):
    """Public thumbnails for the current page, bounded to four people per card."""
    for kind, model in [('post', MatchRegistration), ('tournament', TournamentRegistration)]:
        selected = {ident: card for (k, ident), card in cards.items() if k == kind}
        if not selected:
            continue
        for card in selected.values():
            card['card_participants'] = ([dict(user_id=str(card['user_id']),
                user_nickname=card['user_nickname'], user_avatar=card['user_avatar'])]
                if kind == 'post' else [])
        event_id = model.post_id if kind == 'post' else model.tournament_id
        query = select(event_id.label('event_id'), User.id.label('user_id'),
            User.nickname.label('user_nickname'), User.avatar_url.label('user_avatar'),
            func.row_number().over(partition_by=event_id,
                order_by=(model.created_at, model.id)).label('position')).join(User, User.id == model.user_id)
        query = query.where(event_id.in_(selected))
        if kind == 'post':
            query = query.join(MatchPost, MatchPost.id == model.post_id).where(
                model.status == RegistrationStatus.approved, model.user_id != MatchPost.user_id)
        else:
            query = query.where(model.status == TournamentRegStatus.confirmed,
                model.admission == 'active', model.approval == 'approved',
                model.payment.in_(['none', 'paid', 'verified']))
        ranked = query.subquery()
        rows = (await db.execute(select(ranked).where(ranked.c.position <= (3 if kind == 'post' else 4))
            .order_by(ranked.c.event_id, ranked.c.position))).mappings().all()
        for row in rows:
            selected[row['event_id']]['card_participants'].append(dict(
                user_id=str(row['user_id']), user_nickname=row['user_nickname'], user_avatar=row['user_avatar']))

async def list_activities(db, city, activity_type='all', ntrp_levels=None, on_date=None,
                          sort_by='date_asc', lat=None, lng=None, page=1, page_size=20, status=None):
    branches=[]
    selected_city=city_name(city)
    for kind, model, factory in [('post',MatchPost,posts.discovery_query),('tournament',Tournament,tournaments.discovery_query)]:
        if kind=='tournament' and activity_type in ('post','free','venue') or kind=='post' and activity_type=='tournament':
            continue
        city_column=case((model.venue_id.is_not(None),Venue.city),else_=model.city)
        latitude=case((model.venue_id.is_not(None),Venue.latitude),else_=model.latitude)
        longitude=case((model.venue_id.is_not(None),Venue.longitude),else_=model.longitude)
        if kind=='post':
            if db.bind.dialect.name=='sqlite':
                stamp=func.datetime(cast(model.preferred_date,String) + literal(' ') + func.strftime('%H:%M:%S',model.preferred_start),'-8 hours')
            else:
                stamp=func.timestamp(model.preferred_date,model.preferred_start)-text('INTERVAL 8 HOUR')
        else: stamp=model.start_time
        q=factory().where(public_listing_condition(kind,datetime.utcnow()))
        q=q.where(city_column==selected_city) if selected_city else q.where(False)
        if kind=='post' and activity_type in ('free','venue'):
            q=q.where(model.venue_id.is_(None) if activity_type=='free' else model.venue_id.is_not(None))
        if status:q=q.where(model.status==status)
        if on_date:
            if kind=='post':q=q.where(model.preferred_date==on_date)
            else:
                start=datetime.combine(on_date,datetime.min.time())-timedelta(hours=8)
                q=q.where(model.start_time>=start,model.start_time<start+timedelta(days=1))
        if ntrp_levels:
            values=(await db.execute(q.with_only_columns(model.level_required).distinct())).scalars().all()
            matched=[v for v in values if posts._level_matches(ntrp_levels.split(','),v)]
            q=q.where(model.level_required.in_(matched))
        branches.append(q.with_only_columns(model.id.label('id'),literal(kind).label('kind'),stamp.label('starts'),latitude.label('lat'),longitude.label('lng')).distinct())
    union=branches[0].union_all(*branches[1:]).subquery() if len(branches)>1 else branches[0].subquery()
    total=await db.scalar(select(func.count()).select_from(union)) or 0
    query=ordered(select(union.c.id,union.c.kind),sort_by,union.c.starts,union.c.id,lat,lng,union.c.lat,union.c.lng)
    seats=(await db.execute(query.offset((page-1)*page_size).limit(page_size))).all()
    cards={}
    for kind,model,factory,serializer in [('post',MatchPost,posts.discovery_query,posts.discovery_items),('tournament',Tournament,tournaments.discovery_query,tournaments.discovery_items)]:
        ids=[ident for ident,k in seats if k==kind]
        if not ids:continue
        rows=(await db.execute(factory().where(model.id.in_(ids)))).all()
        items=serializer(rows,lat,lng) if kind=='post' else await serializer(db,rows,lat,lng)
        for item in items:
            data=item.model_dump() if kind=='post' else item
            cards[(kind,data['id'])]=dict(**data,kind=kind)
    await load_card_participants(db, cards)
    return dict(items=[cards[(kind,ident)] for ident,kind in seats],total=total,page=page,page_size=page_size)
