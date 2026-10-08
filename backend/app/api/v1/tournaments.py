from datetime import datetime, timedelta, date as Date
import secrets
import random
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import get_settings
from app.core.rate_limit import check_rate_limit
from app.api.deps import get_current_user, get_optional_user, get_club_admin, _v
from app.models.models import (
    Tournament,
    TournamentRegistration,
    TournamentRegStatus,
    TournamentDraw,
    TournamentTeam,
    TournamentTeamMember,
    TournamentMatch,
    TournamentAudit,
    BookingOrder,
    Club,
    User,
    Venue,
    TournamentStatus,
    Notification, NotificationType,
)
from app.schemas.tournament import (
    TournamentCreate,
    RegistrationCommand,
    ReasonCommand,
    ReviewCommand,
    DrawCommand,
    VersionCommand,
    ResultCommand,
    ScheduleCommand,
    TieCommand,
)
from app.services import tournament_lifecycle as life
from app.services import tournament_engine as engine
from app.services import activity_ids
from app.services.discovery import city_name, ordered
from app.api.v1.posts import haversine

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def row_dict(row, names):
    return {k: getattr(row, k) for k in names.split()}


def brief(t):
    data = row_dict(
        t,
        "id club_id city latitude longitude title sport_type start_time end_time venue_id entry_fee max_participants current_participants cover_image created_at",
    )
    data["activity_id"] = t.id
    data["status"] = _v(t.status)
    return data


async def admin(db, t, user):
    # Creation audit is server-authored and remains the source of creator ownership.
    creator = await db.scalar(select(TournamentAudit.id).where(
        TournamentAudit.tournament_id == t.id,
        TournamentAudit.action == "created",
        TournamentAudit.actor_id == user.id,
    ).limit(1))
    if creator is not None:
        return user
    return await get_club_admin(t.club_id, user, db)


async def require_host_club(db, club_id):
    if club_id is None: return
    club = await db.get(Club, club_id)
    if not club or club.approval_status != "approved" or _v(club.status) != "active":
        raise HTTPException(422, "请选择已审核通过的主办俱乐部")


async def is_admin(db, t, user):
    if not user:
        return False
    try:
        await admin(db, t, user)
        return True
    except HTTPException:
        return False


async def own(db, t, user):
    r = (
        await db.execute(
            select(TournamentRegistration)
            .where(
                TournamentRegistration.tournament_id == t.id,
                TournamentRegistration.user_id == user.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "尚未报名")
    return r


async def draw_for(db, t, version=None):
    version = t.draw_version if version is None else version
    return (
        await db.execute(
            select(TournamentDraw).where(
                TournamentDraw.tournament_id == t.id, TournamentDraw.version == version
            )
        )
    ).scalar_one_or_none()


async def matches_for(db, d):
    if not d:
        return []
    return list(
        (
            await db.execute(
                select(TournamentMatch)
                .where(TournamentMatch.draw_id == d.id)
                .order_by(
                    TournamentMatch.group_no,
                    TournamentMatch.round_no,
                    TournamentMatch.position,
                )
            )
        )
        .scalars()
        .all()
    )


def match_dict(m):
    data = row_dict(
        m,
        "id group_no round_no position kind team_a_id team_b_id source_outcome winner_id score is_draw walkover status court scheduled_at scheduled_end",
    )
    data.update(
        key=str(m.id),
        source_a=str(m.source_a_id) if m.source_a_id else None,
        source_b=str(m.source_b_id) if m.source_b_id else None,
    )
    return data


async def teams_for(db, d):
    teams = (
        list(
            (
                await db.execute(
                    select(TournamentTeam).where(TournamentTeam.draw_id == d.id)
                )
            )
            .scalars()
            .all()
        )
        if d
        else []
    )
    members = (
        list(
            (
                await db.execute(
                    select(TournamentTeamMember).where(
                        TournamentTeamMember.draw_id == d.id
                    )
                )
            )
            .scalars()
            .all()
        )
        if d
        else []
    )
    return [
        dict(
            id=t.id,
            name=t.name,
            group_no=t.group_no,
            origin_group=t.origin_group,
            user_ids=[m.user_id for m in members if m.team_id == t.id],
        )
        for t in teams
    ]


async def rankings(db, d, matches):
    if not d:
        return []
    teams = await teams_for(db, d)
    result = []
    for group in sorted({t["group_no"] for t in teams}):
        ids = [t["id"] for t in teams if t["group_no"] == group]
        ms = [match_dict(m) for m in matches if m.group_no == group]
        if any(m["kind"] == "round_robin" for m in ms):
            rows = engine.standings(ids, ms, (d.tie_orders or {}).get(str(group)))
            for row in rows:
                row["group_no"] = group
            result += rows
        else:
            final_round = max(
                (m["round_no"] for m in ms if m["kind"] == "knockout"), default=1
            )
            for ident in ids:
                lost = next(
                    (
                        m
                        for m in ms
                        if m["status"] in ("completed", "bye")
                        and ident in (m["team_a_id"], m["team_b_id"])
                        and m["winner_id"] != ident
                        and m["kind"] == "knockout"
                    ),
                    None,
                )
                final = next(
                    (
                        m
                        for m in ms
                        if m["kind"] == "knockout" and m["round_no"] == final_round
                    ),
                    None,
                )
                rank = (
                    (2 ** (final_round - lost["round_no"]) + 1)
                    if lost
                    else (1 if final and final["winner_id"] == ident else None)
                )
                third = next(
                    (
                        m
                        for m in ms
                        if m["kind"] == "third_place"
                        and m["status"] in ("completed", "bye")
                    ),
                    None,
                )
                if third and ident in (third["team_a_id"], third["team_b_id"]):
                    rank = 3 if ident == third["winner_id"] else 4
                result.append(
                    dict(team_id=ident, group_no=group, rank=rank, tie_unresolved=False)
                )
    return result


@router.get("")
async def list_tournaments(
    club_id: int | None = None, sport: str | None = None, status: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db), city: str | None = None,
    sort_by: str = Query('date_asc',pattern='^(created|distance|date_asc|date_desc)$'),
    lat: float | None = Query(None,ge=-90,le=90), lng: float | None = Query(None,ge=-180,le=180),
    on_date: Date | None = None,
):
    venue_lat=case((Tournament.venue_id.is_not(None),Venue.latitude),else_=Tournament.latitude)
    venue_lng=case((Tournament.venue_id.is_not(None),Venue.longitude),else_=Tournament.longitude)
    query = select(Tournament, Club.name, venue_lat, venue_lng, case((Tournament.venue_id.is_not(None),Venue.city),else_=Tournament.city)).outerjoin(Club, Tournament.club_id == Club.id).outerjoin(Venue, Tournament.venue_id == Venue.id)
    selected_city=city_name(city)
    effective_city=case((Tournament.venue_id.is_not(None),Venue.city),else_=Tournament.city)
    query=query.where(effective_city==selected_city) if selected_city else query.where(False)
    if club_id: query=query.where(Tournament.club_id==club_id)
    if sport: query=query.where(Tournament.sport_type==sport)
    if status: query=query.where(Tournament.status==status)
    if on_date:
        start=datetime.combine(on_date,datetime.min.time())-timedelta(hours=8)
        query=query.where(Tournament.start_time>=start,Tournament.start_time<start+timedelta(days=1))
    total=(await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    query=ordered(query,sort_by,Tournament.start_time,Tournament.id,lat,lng,
                  venue_lat,venue_lng)
    rows=(await db.execute(query.offset((page-1)*page_size).limit(page_size))).all()
    return dict(items=[dict(**{**brief(t), "city": actual_city, "latitude": clat, "longitude": clng},club_name=name,distance=haversine(lat,lng,
         clat,clng))
         for t,name,clat,clng,actual_city in rows],total=total,page=page,page_size=page_size)


@router.post("/preview")
async def preview(
    req: TournamentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_host_club(db, req.club_id)
    if not req.config:
        raise HTTPException(422, "请选择赛制")
    count = req.max_participants // (1 if req.config.discipline == "singles" else 2)
    groups, matches = engine.build(list(range(1, count + 1)), req.config, "preview")
    engine.schedule(matches, req.config, req.start_time)
    finish = max(
        (m.get("scheduled_end", req.start_time) for m in matches),
        default=req.start_time,
    )
    knockout_preview = None
    if req.config.format == "groups_knockout":
        ids = list(
            range(1, req.config.group_count * req.config.qualifiers_per_group + 1)
        )
        playoff = engine.knockout(ids, third_place=req.config.third_place)
        engine.schedule(playoff, req.config, finish)
        finish = max((m.get("scheduled_end", finish) for m in playoff), default=finish)
        knockout_preview = dict(
            teams=[dict(id=i, name=f"晋级队伍{i}", group_no=1) for i in ids],
            matches=playoff,
        )
    return dict(
        knockout_preview=knockout_preview,
        teams=[
            dict(id=i, name=f"选手/队伍{i}", group_no=g)
            for g, ids in enumerate(groups, 1)
            for i in ids
        ],
        matches=matches,
        total_matches=sum(m.get("status") != "bye" for m in matches)
        + (
            sum(m.get("status") != "bye" for m in knockout_preview["matches"])
            if knockout_preview
            else 0
        ),
        rounds=max(m["round_no"] for m in matches)
        + (
            max(m["round_no"] for m in knockout_preview["matches"])
            if knockout_preview
            else 0
        ),
        estimated_minutes=int((finish - req.start_time).total_seconds() / 60),
        overflows=finish > req.end_time,
        note="虚拟选手预览，正式签表须由管理员抽签发布",
    )


async def apply_request(db, t, req):
    if req.venue_id:
        v = await db.get(Venue, req.venue_id)
        if not v:
            raise HTTPException(422, "场地不存在")
    if req.lock_venue:
        raise HTTPException(
            422, "请先通过订场流程预订场地；赛事排场不会自动锁定预约时段"
        )
    fields = req.model_dump(exclude={"config"})
    fields["city"] = city_name(req.city)
    if req.venue_id:
        fields.update(city=v.city,latitude=v.latitude,longitude=v.longitude,address=v.address)
    for key, value in fields.items():
        setattr(t, key, value)
    if req.auto_title:
        local = req.start_time + timedelta(hours=8)
        t.title = f"{local:%Y-%m-%d} 网球比赛"
    t.config = req.config.model_dump() if req.config else None
    t.cover_image = req.images[0] if req.images else req.cover_image


@router.post("")
async def create_tournament(
    req: TournamentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_host_club(db, req.club_id)
    t = Tournament(id=await activity_ids.allocate_activity(db, "tournament"))
    await apply_request(db, t, req)
    db.add(t)
    await db.flush()
    await db.refresh(t)
    life.audit(db, t, user, "created", {})
    return brief(t)


@router.put("/{ident}")
async def update_tournament(
    ident: int,
    req: TournamentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    if req.club_id != t.club_id:
        raise HTTPException(422, "不可变更主办俱乐部")
    regs = await life.registrations(db, t)
    if t.roster_frozen or t.draw_version:
        raise HTTPException(409, "名单冻结后不能修改赛事配置")
    if regs and (
        t.entry_fee != req.entry_fee
        or (
            t.config is not None
            and t.config != (req.config.model_dump() if req.config else None)
        )
        or req.max_participants < (t.max_participants or req.max_participants)
    ):
        raise HTTPException(409, "已有报名时不能修改费用、赛制或减少名额")
    if t.venue_id and req.venue_id != t.venue_id:
        raise HTTPException(409, "已关联球场的比赛不能变更地点")
    await apply_request(db, t, req)
    life.audit(db, t, user, "updated", {})
    await db.flush()
    return brief(t)


@router.get("/{ident}")
async def get_tournament(
    ident: int,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await db.get(Tournament, ident)
    if not t:
        raise HTTPException(404, "赛事不存在")
    manage = await is_admin(db, t, user)
    can_review = bool(user and await db.scalar(select(TournamentAudit.id).where(
        TournamentAudit.tournament_id == t.id, TournamentAudit.action == "created",
        TournamentAudit.actor_id == user.id).limit(1)))
    d = await draw_for(db, t, t.draw_version if manage else t.published_version)
    rows = (
        await db.execute(
            select(TournamentRegistration, User.nickname, User.avatar_url)
            .join(User, TournamentRegistration.user_id == User.id)
            .where(TournamentRegistration.tournament_id == ident)
            .order_by(TournamentRegistration.created_at)
        )
    ).all()
    regs = []
    mine = None
    for r, nick, avatar in rows:
        public = dict(
            id=r.id,
            user_id=r.user_id,
            user_nickname=nick,
            user_avatar=avatar,
            status=_v(r.status),
            partner_user_id=r.partner_user_id,
            requested_group=r.requested_group,
        )
        private = row_dict(
            r,
            "approval payment admission gender pairing seat_expires_at review_reason invite_token",
        )
        if manage or (user and user.id == r.user_id):
            public.update(private)
            if r.order_id:
                order = await db.get(BookingOrder, r.order_id)
                public["refund_status"] = (
                    _v(order.refund_status) if order and order.refund_status else None
                )
        if user and user.id == r.user_id:
            mine = dict(public)
            if r.order_id:
                o = await db.get(BookingOrder, r.order_id)
                mine["refund_status"] = (
                    _v(o.refund_status) if o and o.refund_status else None
                )
        if (
            manage
            or life.eligible(r)
            or (
                not t.config and _v(r.status) == "confirmed" and r.admission == "active"
            )
        ):
            regs.append(public)
    matches = await matches_for(db, d)
    frozen_ids = {uid for team in await teams_for(db, d) for uid in team["user_ids"]}
    for r, nick, avatar in rows:
        if r.user_id in frozen_ids and not any(x["user_id"] == r.user_id for x in regs):
            regs.append(
                dict(
                    id=r.id,
                    user_id=r.user_id,
                    user_nickname=nick,
                    user_avatar=avatar,
                    status=_v(r.status),
                    partner_user_id=r.partner_user_id,
                    requested_group=r.requested_group,
                )
            )
    club = await db.get(Club, t.club_id) if t.club_id else None
    data = dict(
        **brief(t),
        club_name=club.name if club else None,
        **row_dict(
            t,
            "description prize images address contact_name contact_phone lock_venue config registration_deadline cancellation_deadline registration_closed roster_frozen",
        ),
    )
    if t.venue_id:
        venue = await db.get(Venue, t.venue_id)
        if venue:
            data.update(city=venue.city, address=venue.address, latitude=venue.latitude, longitude=venue.longitude)
    data["auto_title"] = t.auto_title
    data["description_template"] = t.description
    local_start = t.start_time + timedelta(hours=8)
    local_end = t.end_time + timedelta(hours=8)
    data["description"] = (
        (t.description or "")
        .replace("{{日期}}", f"{local_start:%Y-%m-%d}")
        .replace("{{时间}}", f"{local_start:%H:%M} — {local_end:%Y-%m-%d %H:%M}")
        .replace("{{地点}}", data["address"] or "")
        .replace("{{项目}}", "网球")
    )
    closed = t.registration_closed or life.now() >= (
        t.registration_deadline or t.start_time
    )
    data.update(
        registrations=regs,
        my_registration=mine,
        can_manage=manage,
        can_review=can_review,
        can_register=not closed and _v(t.status) == "open",
        draw_version=t.draw_version if manage else t.published_version,
        published_version=t.published_version,
        draw_stage=d.stage if d else None,
        draw_published=bool(d and d.published_at),
        teams=await teams_for(db, d),
        matches=[match_dict(m) for m in matches],
        rankings=await rankings(db, d, matches),
        prepay_enabled=get_settings().TOURNAMENT_PREPAY_ENABLED,
    )
    data["my_draw"] = (
        engine.personal_position(data["teams"], data["matches"], user.id)
        if user
        else None
    )
    active = [
        r for r, _, _ in rows if r.admission == "active" and r.approval == "approved"
    ]
    data["registration_groups"] = [
        dict(
            group_no=g,
            capacity=life.group_capacity(t, g),
            reserved=sum(r.requested_group == g for r in active),
        )
        for g in range(1, (life.config(t).group_count if t.config else 1) + 1)
    ]
    if not d and t.config:
        cfg = life.config(t)
        count = (t.max_participants or 16) // (1 if cfg.discipline == "singles" else 2)
        try:
            groups, template = engine.build(list(range(1, count + 1)), cfg, "template")
            data["bracket_preview"] = dict(
                teams=[
                    dict(id=i, name="待抽签", group_no=g)
                    for g, ids in enumerate(groups, 1)
                    for i in ids
                ],
                matches=template,
            )
        except ValueError:
            data["bracket_preview"] = None
    if not t.published_version and t.config:
        roster = [
            row_dict(r, "user_id gender pairing partner_user_id requested_group")
            for r, _, _ in rows
            if life.eligible(r)
        ]
        try:
            cfg = life.config(t)
            grouped = engine.pair_grouped(
                roster, cfg, f"preview-{t.id}", t.max_participants or 128
            )
            preview_teams = [
                dict(id=i, group_no=g, name=f"队伍{i}", user_ids=players)
                for i, (g, players) in enumerate(grouped, 1)
            ]
            preview_matches = []
            for g in range(1, cfg.group_count + 1):
                ids = [team["id"] for team in preview_teams if team["group_no"] == g]
                preview_matches += (
                    engine.knockout(ids, g, cfg.third_place)
                    if cfg.format == "knockout"
                    else engine.round_robin(ids, g)
                )
            engine.schedule(preview_matches, cfg, t.start_time)
            data["participant_preview"] = dict(
                my_draw=engine.personal_position(preview_teams, preview_matches, user.id) if user else None,
                teams=preview_teams,
                matches=preview_matches,
                note="临时对阵预览，随报名变化，正式签表以主办方发布为准",
            )
        except ValueError:
            data["participant_preview"] = None
    data["history"] = [
        dict(
            version=x.version,
            stage=x.stage,
            published=bool(x.published_at),
            reason=x.reason,
        )
        for x in (
            await db.execute(
                select(TournamentDraw)
                .where(TournamentDraw.tournament_id == ident)
                .order_by(TournamentDraw.version)
            )
        )
        .scalars()
        .all()
        if manage or x.published_at
    ]
    return data


@router.get("/{ident}/draws/{version}")
async def get_draw(
    ident: int,
    version: int,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await db.get(Tournament, ident)
    if not t:
        raise HTTPException(404, "赛事不存在")
    d = await draw_for(db, t, version)
    if not d or (not d.published_at and not await is_admin(db, t, user)):
        raise HTTPException(404, "签表未发布")
    ms = await matches_for(db, d)
    return dict(
        version=d.version,
        stage=d.stage,
        teams=await teams_for(db, d),
        matches=[match_dict(m) for m in ms],
        rankings=await rankings(db, d, ms),
    )


@router.post("/{ident}/register")
async def register_tournament(
    ident: int,
    req: RegistrationCommand = RegistrationCommand(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await life.refresh_admissions(db, t)
    if t.registration_closed or _v(t.status) != "open":
        raise HTTPException(409, "报名已关闭")
    if t.entry_fee > 0 and not get_settings().TOURNAMENT_PREPAY_ENABLED:
        raise HTTPException(503, "赛事线上支付尚未开放")
    cfg = life.config(t) if t.config else None
    if cfg and cfg.discipline == "mixed" and not req.gender:
        raise HTTPException(422, "混双报名需要填写性别")
    r = (
        await db.execute(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == ident,
                TournamentRegistration.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if r and r.admission not in ("cancelled", "expired", "rejected"):
        raise HTTPException(409, "已经报名")
    if not r:
        r = TournamentRegistration(tournament_id=ident, user_id=user.id)
        db.add(r)
    life.group_capacity(t, req.requested_group)
    r.requested_group = req.requested_group
    r.gender = req.gender
    r.pairing = req.pairing
    r.partner_user_id = None
    r.invite_token = None
    r.order_id = None
    r.approval = "pending" if cfg and cfg.approval_required else "approved"
    r.payment = "none"
    r.admission = "review"
    r.status = TournamentRegStatus.registered
    r.created_at = life.now()
    r.review_reason = None
    await db.flush()
    if r.approval == "approved":
        await life.admit(db, t, r)
    life.audit(db, t, user, "registered", {"registration_id": r.id})
    return dict(
        msg="ok",
        registration_id=r.id,
        admission=r.admission,
        payment=r.payment,
        order={"id": r.order_id} if r.order_id else None,
    )


@router.post("/{ident}/registrations/{reg_id}/review")
async def review(
    ident: int,
    reg_id: int,
    req: ReviewCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    creator = await db.scalar(select(TournamentAudit.id).where(
        TournamentAudit.tournament_id == t.id, TournamentAudit.action == "created",
        TournamentAudit.actor_id == user.id).limit(1))
    if creator is None:
        raise HTTPException(403, "只有比赛发起者可以审核报名")
    await life.refresh_admissions(db, t)
    if t.roster_frozen:
        raise HTTPException(409, "名单已冻结")
    r = await db.get(TournamentRegistration, reg_id)
    if not r or r.tournament_id != ident or r.approval != "pending":
        raise HTTPException(409, "没有待审核报名")
    r.review_reason = req.reason
    r.approval = "approved" if req.approved else "rejected"
    if req.approved:
        await life.admit(db, t, r)
    else:
        r.admission = "rejected"
        r.status = TournamentRegStatus.cancelled
    life.audit(
        db,
        t,
        user,
        "reviewed",
        {"registration_id": r.id, "approved": req.approved, "reason": req.reason},
    )
    db.add(Notification(user_id=r.user_id, type=NotificationType.tournament,
        title="比赛报名已通过" if req.approved else "比赛报名未通过",
        content=f"《{t.title}》" + ("报名已通过。" if req.approved else f"报名未通过：{req.reason}"),
        ref_id=t.id, ref_type="tournament"))
    return {"msg": "ok"}


@router.post("/{ident}/registrations/{reg_id}/cancel")
async def cancel_registration(
    ident: int,
    reg_id: int,
    req: ReasonCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    r = await db.get(TournamentRegistration, reg_id)
    if not r or r.tournament_id != ident:
        raise HTTPException(404, "报名不存在")
    manage = await is_admin(db, t, user)
    if r.user_id != user.id and not manage:
        raise HTTPException(403, "不能取消他人报名")
    if r.admission in ("cancelled", "expired", "rejected"):
        return {"msg": "ok"}
    if not manage and (
        t.roster_frozen
        or life.now() >= (t.cancellation_deadline or t.start_time - timedelta(hours=1))
    ):
        raise HTTPException(409, "已超过自助取消截止时间，请联系管理员")
    if t.draw_version:
        raise HTTPException(409, "已有签表，请使用管理员退款或取消整个赛事")
    await life.cancel_registration(db, t, r, req.reason, user)
    return {"msg": "ok"}


@router.post("/{ident}/registrations/{reg_id}/refund")
async def refund_registration(
    ident: int,
    reg_id: int,
    req: ReasonCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    r = await db.get(TournamentRegistration, reg_id)
    if not r or r.tournament_id != ident or not r.order_id:
        raise HTTPException(404, "无报名订单")
    o = await life.locked_order(db, r.order_id)
    if _v(o.status) not in ("paid", "refunding", "refunded"):
        raise HTTPException(409, "订单未真实支付")
    if _v(o.status) != "refunded":
        await life.cancel_registration(db, t, r, req.reason, user)
        await life.request_refund(db, o, req.reason)
    life.audit(
        db, t, user, "admin_refund", {"registration_id": reg_id, "reason": req.reason}
    )
    return {"msg": "ok"}


@router.post("/{ident}/registrations/{reg_id}/verify-payment")
async def verify_legacy(
    ident: int,
    reg_id: int,
    req: ReasonCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    r = await db.get(TournamentRegistration, reg_id)
    if (
        not r
        or r.tournament_id != ident
        or r.payment != "unverified"
        or t.roster_frozen
    ):
        raise HTTPException(409, "没有待核验的历史报名，或名单已冻结")
    r.payment = "verified"
    r.status = TournamentRegStatus.confirmed
    await life.refresh_admissions(db, t)
    life.audit(
        db,
        t,
        user,
        "legacy_registration_verified",
        {"registration_id": r.id, "reason": req.reason},
    )
    return {"msg": "ok", "note": "仅核验参赛资格，未伪造微信收款或退款依据"}


@router.post("/{ident}/group")
async def select_group(
    ident: int,
    req: RegistrationCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    rows = await life.refresh_admissions(db, t)
    if t.roster_frozen or _v(t.status) != "open":
        raise HTTPException(409, "名单已冻结，不能更改分组")
    r = await own(db, t, user)
    if r.admission not in ("active", "review", "waitlisted"):
        raise HTTPException(409, "当前报名不能选组")
    life.group_capacity(t, req.requested_group)
    if r.partner_user_id and r.requested_group != req.requested_group:
        raise HTTPException(409, "请先解除固定搭档，再重新选组和确认搭档")
    r.requested_group = req.requested_group
    if r.admission == "active" and not life.group_available(
        t, r, [p for p in rows if p.admission == "active" and p.approval == "approved"]
    ):
        raise HTTPException(409, "该组名额已满或混双性别名额已满")
    life.audit(
        db,
        t,
        user,
        "group_selected",
        {"registration_id": r.id, "group_no": req.requested_group},
    )
    return {"msg": "ok"}


@router.post("/{ident}/pairing")
async def pairing(
    ident: int,
    req: RegistrationCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await life.refresh_admissions(db, t)
    r = await own(db, t, user)
    if t.roster_frozen or r.admission in ("cancelled", "expired", "rejected"):
        raise HTTPException(409, "当前不能调整搭档")
    if life.config(t).discipline == "singles":
        raise HTTPException(409, "单打无需搭档")
    await life.unpair(db, t, r)
    r.pairing = req.pairing
    r.invite_token = secrets.token_urlsafe(24) if req.pairing == "fixed" else None
    return dict(invite_token=r.invite_token)


@router.post("/{ident}/invitations/{token}/accept")
async def accept_invitation(
    ident: int,
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await life.refresh_admissions(db, t)
    if t.roster_frozen:
        raise HTTPException(409, "名单已冻结")
    sender = (
        await db.execute(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == ident,
                TournamentRegistration.invite_token == token,
            )
        )
    ).scalar_one_or_none()
    receiver = await own(db, t, user)
    if (
        not sender
        or sender.user_id == user.id
        or sender.partner_user_id
        or receiver.partner_user_id
        or sender.admission not in ("active", "waitlisted", "review")
        or receiver.admission not in ("active", "waitlisted", "review")
    ):
        raise HTTPException(409, "搭档邀请失效或已组队")
    if life.config(t).discipline == "mixed" and {sender.gender, receiver.gender} != {
        "male",
        "female",
    }:
        raise HTTPException(422, "混双搭档必须一男一女")
    if sender.requested_group != receiver.requested_group:
        raise HTTPException(409, "固定搭档须选择相同分组（或双方均选自动分组）")
    sender.partner_user_id = user.id
    receiver.partner_user_id = sender.user_id
    sender.pairing = receiver.pairing = "fixed"
    sender.invite_token = None
    receiver.invite_token = None
    life.audit(db, t, user, "partner_confirmed", {"users": [sender.user_id, user.id]})
    return {"msg": "ok"}


@router.post("/{ident}/pay")
async def pay_tournament(
    ident: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    await check_rate_limit(
        f"rate:pay:{user.id}",
        max_requests=get_settings().RATE_LIMIT_PAY_PER_MINUTE,
        window_seconds=60,
    )
    t = await life.locked_event(db, ident)
    return await life.pay(db, t, await own(db, t, user), user)


@router.post("/{ident}/payment-status")
async def payment_status(
    ident: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    r = await own(db, t, user)
    if r.order_id and r.payment == "pending":
        o = await life.locked_order(db, r.order_id)
        data = await life.wx_call("query", out_trade_no=o.order_no)
        if data.get("trade_state") == "SUCCESS":
            await life.payment_success(db, data)
    await life.refresh_admissions(db, t)
    return dict(payment=r.payment, admission=r.admission, status=_v(r.status))


@router.post("/{ident}/close-registration")
async def close_registration(
    ident: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    t.registration_closed = True
    t.roster_frozen = True
    life.audit(db, t, user, "roster_frozen", {})
    return {"msg": "ok"}


async def persist_matches(db, d, rows):
    ids = {}
    for row in rows:
        data = {
            k: v for k, v in row.items() if k not in ("key", "source_a", "source_b")
        }
        data["source_a_id"] = ids.get(row.get("source_a"))
        data["source_b_id"] = ids.get(row.get("source_b"))
        m = TournamentMatch(draw_id=d.id, **data)
        db.add(m)
        await db.flush()
        ids[row["key"]] = m.id


@router.post("/{ident}/draw")
async def create_draw(
    ident: int,
    req: DrawCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    regs = await life.refresh_admissions(db, t)
    cfg = life.config(t)
    prior = (
        await db.execute(
            select(TournamentDraw).where(
                TournamentDraw.tournament_id == ident,
                TournamentDraw.idempotency_key == req.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if prior:
        return {"version": prior.version}
    if _v(t.status) in ("cancelled", "finished"):
        raise HTTPException(409, "赛事已结束或取消")
    if not t.roster_frozen:
        raise HTTPException(409, "请先关闭报名并冻结名单")
    if req.expected_version != t.draw_version:
        raise HTTPException(409, "签表版本已变化，请刷新")
    old = await draw_for(db, t)
    old_matches = await matches_for(db, old)
    superseded_version = old.version if old else None
    played = any(m.status == "completed" for m in old_matches)
    if old and old.stage == "knockout" and req.stage == "initial":
        raise HTTPException(409, "不能回退已完成的小组赛，请重抽当前淘汰阶段")
    if (
        old
        and req.stage == "initial"
        and (not req.reason.strip() or (played and not req.archive_results))
    ):
        raise HTTPException(409, "重抽须填写原因；已有结果时须明确确认归档旧结果")
    seed = secrets.token_hex(16)
    snapshot = {}
    origins = {}
    if req.stage == "knockout":
        if cfg.format != "groups_knockout" or not old:
            raise HTTPException(409, "当前不能生成淘汰阶段")
        if old.stage == "knockout":
            if not req.reason.strip() or (played and not req.archive_results):
                raise HTTPException(
                    409, "重抽须填写原因；已有结果时须明确确认归档旧结果"
                )
            old = await draw_for(db, t, old.snapshot["source_version"])
            old_matches = await matches_for(db, old)
        if not old.published_at:
            raise HTTPException(409, "请先发布小组赛签表")
        if any(m.status != "completed" for m in old_matches):
            raise HTTPException(409, "小组赛尚未全部完成")
        ranks = await rankings(db, old, old_matches)
        oldteams = await teams_for(db, old)
        chosen = []
        for group in range(1, cfg.group_count + 1):
            group_rows = [r for r in ranks if r["group_no"] == group]
            if len(group_rows) < cfg.qualifiers_per_group or any(
                r["tie_unresolved"] for r in group_rows
            ):
                raise HTTPException(409, "请先处理同分排名或调整晋级人数")
            chosen += [r["team_id"] for r in group_rows[: cfg.qualifiers_per_group]]
        players = [next(x for x in oldteams if x["id"] == i) for i in chosen]
        snapshot = {
            "source_version": old.version,
            "qualifiers": chosen,
            "roster": old.snapshot.get("roster", []),
        }
    else:
        roster = [
            row_dict(r, "user_id gender pairing partner_user_id requested_group")
            for r in regs
            if life.eligible(r)
        ]
        try:
            grouped = engine.pair_grouped(roster, cfg, seed, t.max_participants or 128)
            paired = [pair for group, pair in grouped]
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if len(paired) < 2 * cfg.group_count:
            raise HTTPException(409, "每组至少需要两队")
        players = [dict(user_ids=p, group_no=g, origin_group=None) for g, p in grouped]
        snapshot = {"roster": roster}
    d = TournamentDraw(
        tournament_id=ident,
        version=t.draw_version + 1,
        stage=req.stage,
        idempotency_key=req.idempotency_key,
        seed=seed,
        snapshot=dict(snapshot, config=cfg.model_dump()),
        created_by=user.id,
        reason=req.reason,
    )
    db.add(d)
    await db.flush()
    team_ids = []
    for i, p in enumerate(players, 1):
        team = TournamentTeam(
            draw_id=d.id, group_no=1, name=f"队伍{i}", origin_group=p.get("group_no")
        )
        db.add(team)
        await db.flush()
        team_ids.append(team.id)
        origins[team.id] = p.get("group_no")
        for uid in p["user_ids"]:
            db.add(TournamentTeamMember(draw_id=d.id, team_id=team.id, user_id=uid))
    try:
        if req.stage == "knockout":
            groups = [team_ids]
            rows = engine.qualified_draw(team_ids, origins, seed, cfg.third_place)
        else:
            groups = [
                [i for i, p in zip(team_ids, players) if p["group_no"] == g]
                for g in range(1, cfg.group_count + 1)
            ]
            rows = []
            for g, ids in enumerate(groups, 1):
                random.Random(seed + str(g)).shuffle(ids)
                rows += (
                    engine.knockout(ids, g, cfg.third_place)
                    if cfg.format == "knockout"
                    else engine.round_robin(ids, g)
                )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    for g, ids in enumerate(groups, 1):
        for i in ids:
            (await db.get(TournamentTeam, i)).group_no = g
    start = (
        max(
            t.start_time,
            max(
                (m.scheduled_end for m in old_matches if m.scheduled_end),
                default=t.start_time,
            ),
        )
        if req.stage == "knockout"
        else t.start_time
    )
    engine.schedule(rows, cfg, start)
    overflow = any(m.get("scheduled_end", start) > t.end_time for m in rows)
    if overflow:
        for m in rows:
            for key in ("court", "scheduled_at", "scheduled_end"):
                m.pop(key, None)
    await persist_matches(db, d, rows)
    t.draw_version = d.version
    if req.publish:
        d.published_at = life.now()
        t.published_version = d.version
        life.audit(db, t, user, "draw_published", {"version": d.version})
    if old and played and req.archive_results:
        life.audit(
            db,
            t,
            user,
            "results_archived",
            {
                "old_version": superseded_version,
                "new_version": d.version,
                "reason": req.reason,
            },
        )
    life.audit(
        db,
        t,
        user,
        "draw_created",
        {"version": d.version, "reason": req.reason, "stage": req.stage},
    )
    return dict(
        version=d.version,
        overflows=overflow,
        note="预计赛程超出赛事时间，请手动排场" if overflow else "",
    )


@router.post("/{ident}/draw/publish")
async def publish_draw(
    ident: int,
    req: VersionCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    d = await draw_for(db, t)
    if (
        not d
        or req.expected_version != d.version
        or _v(t.status) in ("cancelled", "finished")
    ):
        raise HTTPException(409, "签表版本已变化或赛事已结束")
    if not d.published_at:
        d.published_at = life.now()
        t.published_version = d.version
    life.audit(db, t, user, "draw_published", {"version": d.version})
    return {"msg": "ok"}


async def editable(db, t, req, user):
    await admin(db, t, user)
    d = await draw_for(db, t)
    if (
        not d
        or d.version != req.expected_version
        or _v(t.status) in ("cancelled", "finished")
    ):
        raise HTTPException(409, "签表版本变化或赛事已结束")
    return d, await matches_for(db, d)


async def update_resolved(db, matches):
    rows = [match_dict(m) for m in matches]
    engine.resolve(rows)
    for m, data in zip(matches, rows):
        for k in ("team_a_id", "team_b_id", "winner_id", "status"):
            setattr(m, k, data.get(k))


@router.put("/{ident}/matches/{match_id}/result")
async def record_result(
    ident: int,
    match_id: int,
    req: ResultCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    d, ms = await editable(db, t, req, user)
    if not d.published_at:
        raise HTTPException(409, "请先发布签表")
    m = next((m for m in ms if m.id == match_id), None)
    if not m or not m.team_a_id or not m.team_b_id or m.status == "bye":
        raise HTTPException(409, "对阵双方尚未确定")
    downstream = {m.id}
    for other in ms:
        if other.source_a_id in downstream or other.source_b_id in downstream:
            downstream.add(other.id)
            if other.status == "completed":
                raise HTTPException(409, "请先撤销下游比赛结果")
    if m.status == "completed" and not req.reason.strip():
        raise HTTPException(422, "修改结果必须填写原因")
    cfg = life.config(t)
    if req.is_draw:
        if (
            m.kind != "round_robin"
            or not cfg.allow_draw
            or req.winner_id
            or req.walkover
        ):
            raise HTTPException(422, "此比赛不能录入平局")
    elif req.winner_id not in (m.team_a_id, m.team_b_id):
        raise HTTPException(422, "请选择对阵中的胜者")
    m.winner_id = req.winner_id
    m.score = req.score
    m.is_draw = req.is_draw
    m.walkover = req.walkover
    m.status = "completed"
    d.tie_orders = None
    await update_resolved(db, ms)
    t.status = TournamentStatus.ongoing
    life.audit(
        db,
        t,
        user,
        "result_recorded",
        {
            "match_id": m.id,
            "winner_id": req.winner_id,
            "score": req.score,
            "reason": req.reason,
        },
    )
    return {"msg": "ok"}


@router.post("/{ident}/matches/{match_id}/reset")
async def reset_result(
    ident: int,
    match_id: int,
    req: ResultCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    d, ms = await editable(db, t, req, user)
    if not req.reason.strip():
        raise HTTPException(422, "撤销结果须填写原因")
    m = next((m for m in ms if m.id == match_id), None)
    if not m or m.status != "completed":
        raise HTTPException(409, "无可撤销结果")
    descendants = {m.id}
    for other in ms:
        if other.source_a_id in descendants or other.source_b_id in descendants:
            descendants.add(other.id)
            if other.status == "completed":
                raise HTTPException(409, "请先撤销下游比赛结果")
    m.status = "pending"
    m.winner_id = None
    m.score = None
    m.is_draw = False
    m.walkover = False
    d.tie_orders = None
    await update_resolved(db, ms)
    life.audit(db, t, user, "result_reset", {"match_id": m.id, "reason": req.reason})
    return {"msg": "ok"}


@router.put("/{ident}/matches/{match_id}/schedule")
async def schedule_match(
    ident: int,
    match_id: int,
    req: ScheduleCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    d, ms = await editable(db, t, req, user)
    cfg = life.config(t)
    m = next((m for m in ms if m.id == match_id), None)
    end = req.start_time + timedelta(minutes=cfg.match_minutes)
    if (
        not m
        or m.status != "pending"
        or req.court not in cfg.courts
        or req.start_time < t.start_time
        or end > t.end_time
    ):
        raise HTTPException(422, "场地、时间或场次状态无效")
    ancestors = {}

    def potential(x):
        if x.id in ancestors:
            return ancestors[x.id]
        ids = {v for v in (x.team_a_id, x.team_b_id) if v}
        for source in (x.source_a_id, x.source_b_id):
            parent = next((a for a in ms if a.id == source), None)
            if parent:
                ids |= potential(parent)
        ancestors[x.id] = ids
        return ids

    for parent_id in (m.source_a_id, m.source_b_id):
        parent = next((x for x in ms if x.id == parent_id), None)
        if (
            parent
            and parent.status != "bye"
            and (not parent.scheduled_end or parent.scheduled_end > req.start_time)
        ):
            raise HTTPException(409, "必须安排在前置比赛结束之后")
    limit = min(len(cfg.courts), cfg.max_parallel or len(cfg.courts))
    intervals = [(req.start_time, 1), (end, -1)]
    for other in ms:
        if other.id == m.id or not other.scheduled_at or other.status == "bye":
            continue
        if other.scheduled_at < end and other.scheduled_end > req.start_time:
            intervals += [
                (max(req.start_time, other.scheduled_at), 1),
                (min(end, other.scheduled_end), -1),
            ]
            if other.court == req.court or potential(m) & potential(other):
                raise HTTPException(409, "场地或参赛者时间冲突")
        if other.source_a_id == m.id or other.source_b_id == m.id:
            if other.scheduled_at < end:
                raise HTTPException(409, "不能晚于下游场次开始")
    concurrent = 0
    for _, change in sorted(intervals):
        concurrent += change
        if concurrent > limit:
            raise HTTPException(409, "超过同时进行的场次数限制")
    m.court = req.court
    m.scheduled_at = req.start_time
    m.scheduled_end = end
    life.audit(
        db,
        t,
        user,
        "match_scheduled",
        {"match_id": m.id, "court": req.court, "time": req.start_time.isoformat()},
    )
    return {"msg": "ok"}


@router.post("/{ident}/tie-order")
async def tie_order(
    ident: int,
    req: TieCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    d, ms = await editable(db, t, req, user)
    ids = [x["id"] for x in await teams_for(db, d) if x["group_no"] == req.group_no]
    if (
        set(ids) != set(req.team_ids)
        or len(ids) != len(req.team_ids)
        or any(m.status != "completed" for m in ms if m.group_no == req.group_no)
    ):
        raise HTTPException(422, "请提交该组完整队伍顺序，且先完成小组赛")
    d.tie_orders = dict(d.tie_orders or {}, **{str(req.group_no): req.team_ids})
    life.audit(
        db,
        t,
        user,
        "tie_resolved",
        {"group_no": req.group_no, "team_ids": req.team_ids, "reason": req.reason},
    )
    return {"msg": "ok"}


@router.post("/{ident}/finish")
async def finish(
    ident: int,
    req: VersionCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    d, ms = await editable(db, t, req, user)
    if (
        not d.published_at
        or not ms
        or any(m.status not in ("completed", "bye") for m in ms)
    ):
        raise HTTPException(409, "尚有比赛未完成")
    if life.config(t).format == "groups_knockout" and d.stage != "knockout":
        raise HTTPException(409, "请先完成淘汰阶段")
    if any(r["tie_unresolved"] for r in await rankings(db, d, ms)):
        raise HTTPException(409, "请先处理同分排名")
    t.status = TournamentStatus.finished
    life.audit(db, t, user, "finished", {})
    return {"msg": "ok"}


@router.post("/{ident}/cancel")
async def cancel_event(
    ident: int,
    req: ReasonCommand,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await life.locked_event(db, ident)
    await admin(db, t, user)
    t.status = TournamentStatus.cancelled
    t.registration_closed = True
    t.roster_frozen = True
    for r in await life.registrations(db, t):
        await life.cancel_registration(db, t, r, req.reason, user)
    life.audit(db, t, user, "cancelled", {"reason": req.reason})
    return {"msg": "ok"}


@router.get("/{ident}/audit")
async def audit_log(
    ident: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ident = await activity_ids.resolve_activity_id(db, ident, "tournament")
    t = await db.get(Tournament, ident)
    if not t:
        raise HTTPException(404, "赛事不存在")
    await admin(db, t, user)
    return [
        row_dict(x, "id actor_id action detail created_at")
        for x in (
            await db.execute(
                select(TournamentAudit)
                .where(TournamentAudit.tournament_id == ident)
                .order_by(TournamentAudit.id.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    ]
