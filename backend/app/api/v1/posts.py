from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from math import radians, cos, sin, asin, sqrt
from app.core.database import get_db
from app.api.deps import get_current_user, _v
from app.models.models import (
    User, Club, ClubMember, Venue, MatchPost, MatchRegistration, MatchPostStatus,
    RegistrationStatus, Notification, NotificationType,
)
from app.schemas.schemas import (
    PostCreate, PostBrief, PostDetail, PostListParams, PaginatedResponse,
    RegisterPostRequest, ReviewRegistrationRequest, RegistrationBrief,
)

router = APIRouter(prefix="/posts", tags=["posts"])


def _fallback_nickname(user_id: int, phone: str | None) -> str:
    if phone and len(phone) >= 11:
        return phone[:3] + '****' + phone[7:]
    return f'用户{user_id}'


def haversine(lat1, lng1, lat2, lng2):
    """Calculate distance (km) between two points."""
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return None
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Earth radius in km
    return round(c * r, 1)


@router.get("", response_model=PaginatedResponse)
async def list_posts(
    club_id: int = Query(None),
    sport: str = Query(None),
    status: str = Query(None),
    lat: float = Query(None),
    lng: float = Query(None),
    sort_by: str = Query('created', regex='^(created|distance)$'),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MatchPost, User.nickname, User.avatar_url, User.phone, Club.name,
               Club.latitude, Club.longitude,
               func.count(MatchRegistration.id))
        .join(User, MatchPost.user_id == User.id)
        .join(Club, MatchPost.club_id == Club.id)
        .outerjoin(MatchRegistration, MatchRegistration.post_id == MatchPost.id)
    )
    count_query = select(func.count(MatchPost.id))

    if club_id:
        query = query.where(MatchPost.club_id == club_id)
        count_query = count_query.where(MatchPost.club_id == club_id)
    if sport:
        query = query.where(MatchPost.sport_type == sport)
        count_query = count_query.where(MatchPost.sport_type == sport)
    if status:
        query = query.where(MatchPost.status == status)
        count_query = count_query.where(MatchPost.status == status)

    query = query.group_by(MatchPost.id)

    if sort_by == 'distance' and lat is not None and lng is not None:
        # Sort by distance in Python after fetching
        pass  # We'll sort after fetching
    else:
        query = query.order_by(MatchPost.created_at.desc())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for row in rows:
        post, nickname, avatar, phone, club_name, club_lat, club_lng, reg_count = row
        distance = haversine(lat, lng,
                             float(club_lat) if club_lat else None,
                             float(club_lng) if club_lng else None)
        user_nickname = nickname or _fallback_nickname(post.user_id, phone)
        items.append(PostBrief(
            id=post.id, club_id=post.club_id, user_id=post.user_id,
            title=post.title, sport_type=post.sport_type,
            preferred_date=post.preferred_date,
            preferred_start=post.preferred_start,
            preferred_end=post.preferred_end,
            players_needed=post.players_needed,
            level_required=post.level_required,
            status=post.status.value,
            created_at=post.created_at,
            user_nickname=user_nickname, user_avatar=avatar,
            club_name=club_name, registration_count=reg_count or 0,
            distance=distance,
        ))

    if sort_by == 'distance':
        items.sort(key=lambda x: x.distance if x.distance is not None else float('inf'))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=PostBrief)
async def create_post(
    req: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 权限校验：只有俱乐部管理员或平台管理员才能发布
    if _v(current_user.role) not in ("club_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="只有俱乐部管理员才能发布约球帖")

    member_result = await db.execute(
        select(ClubMember).where(
            ClubMember.user_id == current_user.id,
            ClubMember.club_id == req.club_id,
        )
    )
    if not member_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="只有俱乐部管理员才能发布约球帖")

    post = MatchPost(
        club_id=req.club_id,
        user_id=current_user.id,
        title=req.title,
        sport_type=req.sport_type,
        preferred_date=req.preferred_date,
        preferred_start=req.preferred_start,
        preferred_end=req.preferred_end,
        players_needed=req.players_needed,
        level_required=req.level_required,
        notes=req.notes,
        description=req.description,
        documents=req.documents,
        venue_id=req.venue_id,
        booking_id=req.booking_id,
    )
    db.add(post)
    await db.flush()
    await db.refresh(post)

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    club_result = await db.execute(select(Club).where(Club.id == req.club_id))
    club = club_result.scalar_one_or_none()

    return PostBrief(
        id=post.id, club_id=post.club_id, user_id=post.user_id,
        title=post.title, sport_type=post.sport_type,
        preferred_date=post.preferred_date,
        preferred_start=post.preferred_start,
        preferred_end=post.preferred_end,
        players_needed=post.players_needed,
        level_required=post.level_required,
        status=post.status.value,
        created_at=post.created_at,
        user_nickname=user.nickname or _fallback_nickname(user.id, user.phone),
        user_avatar=user.avatar_url,
        club_name=club.name if club else None,
        registration_count=0,
    )


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MatchPost, User.nickname, User.avatar_url, User.phone, Club.name,
               func.count(MatchRegistration.id))
        .join(User, MatchPost.user_id == User.id)
        .join(Club, MatchPost.club_id == Club.id)
        .outerjoin(MatchRegistration, MatchRegistration.post_id == MatchPost.id)
        .where(MatchPost.id == post_id)
        .group_by(MatchPost.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    post, nickname, avatar, phone, club_name, reg_count = row

    # Get registrations
    reg_result = await db.execute(
        select(MatchRegistration, User.nickname, User.avatar_url, User.phone)
        .join(User, MatchRegistration.user_id == User.id)
        .where(MatchRegistration.post_id == post_id)
        .order_by(MatchRegistration.id)
    )
    reg_rows = reg_result.all()

    registrations = []
    for r, r_nick, r_av, r_phone in reg_rows:
        r_nick = r_nick or _fallback_nickname(r.user_id, r_phone)
        registrations.append(RegistrationBrief(
            id=r.id, user_id=r.user_id, message=r.message, status=r.status.value,
            user_nickname=r_nick, user_avatar=r_av,
        ))

    # Get venue info if available
    venue_address = None
    venue_latitude = None
    venue_longitude = None
    cover_image = None
    club_documents = None
    if post.venue_id:
        venue_result = await db.execute(
            select(Venue).where(Venue.id == post.venue_id)
        )
        venue = venue_result.scalar_one_or_none()
        if venue:
            venue_address = venue.address
            cover_image = venue.cover_image
    # Fallback to club info
    if not venue_address:
        club_result = await db.execute(
            select(Club).where(Club.id == post.club_id)
        )
        club = club_result.scalar_one_or_none()
        if club:
            venue_address = club.address
            venue_latitude = float(club.latitude) if club.latitude else None
            venue_longitude = float(club.longitude) if club.longitude else None
            cover_image = cover_image or club.cover_image
            club_documents = club.documents

    # Get user phone
    user_phone = None
    user_result = await db.execute(
        select(User.phone, User.ntrp_level).where(User.id == post.user_id)
    )
    user_row = user_result.one_or_none()
    if user_row:
        user_phone = user_row[0]

    return PostDetail(
        id=post.id, club_id=post.club_id, user_id=post.user_id,
        title=post.title, sport_type=post.sport_type,
        preferred_date=post.preferred_date,
        preferred_start=post.preferred_start,
        preferred_end=post.preferred_end,
        players_needed=post.players_needed,
        level_required=post.level_required,
        status=post.status.value,
        created_at=post.created_at,
        user_nickname=nickname or _fallback_nickname(post.user_id, phone), user_avatar=avatar,
        club_name=club_name, registration_count=reg_count or 0,
        notes=post.notes, description=post.description, documents=post.documents,
        venue_id=post.venue_id, booking_id=post.booking_id,
        registrations=registrations,
        price=None, user_phone=user_phone, venue_address=venue_address,
        venue_latitude=venue_latitude, venue_longitude=venue_longitude,
        cover_image=cover_image, club_documents=club_documents,
    )


@router.post("/{post_id}/register")
async def register_post(
    post_id: int,
    req: RegisterPostRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if _v(post.status) != "open":
        raise HTTPException(status_code=400, detail="Post is not open")

    existing = await db.execute(
        select(MatchRegistration).where(
            MatchRegistration.post_id == post_id,
            MatchRegistration.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already registered")

    reg = MatchRegistration(
        post_id=post_id,
        user_id=current_user.id,
        message=req.message,
        status=RegistrationStatus.pending,
    )
    db.add(reg)

    # Notify post owner
    notif = Notification(
        user_id=post.user_id,
        type=NotificationType.match,
        title="有人报名了你的约球帖",
        content=f"用户 {current_user.nickname or '新用户'} 报名了约球帖《{post.title}》",
        ref_id=post.id,
        ref_type="match_post",
    )
    db.add(notif)

    return {"msg": "ok"}


@router.delete("/{post_id}/register")
async def cancel_register(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MatchRegistration).where(
            MatchRegistration.post_id == post_id,
            MatchRegistration.user_id == current_user.id,
        )
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    await db.delete(reg)
    return {"msg": "ok"}


@router.put("/{post_id}/registrations/{user_id}")
async def review_registration(
    post_id: int,
    user_id: int,
    req: ReviewRegistrationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id and _v(current_user.role) != "platform_admin":
        raise HTTPException(status_code=403, detail="Only post owner can review")

    result = await db.execute(
        select(MatchRegistration).where(
            MatchRegistration.post_id == post_id,
            MatchRegistration.user_id == user_id,
        )
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")

    new_status = RegistrationStatus(req.status)
    reg.status = new_status

    # Notify registrant about approval/rejection
    title_map = {
        RegistrationStatus.approved: "报名已通过",
        RegistrationStatus.rejected: "报名已被拒绝",
    }
    content_map = {
        RegistrationStatus.approved: f"你的报名已通过，约球帖《{post.title}》",
        RegistrationStatus.rejected: f"你的报名被拒绝，约球帖《{post.title}》",
    }
    if new_status in title_map:
        notif = Notification(
            user_id=user_id,
            type=NotificationType.match,
            title=title_map[new_status],
            content=content_map[new_status],
            ref_id=post.id,
            ref_type="match_post",
        )
        db.add(notif)

    # If approved, check if post is now full
    if new_status == RegistrationStatus.approved:
        approved_count_result = await db.execute(
            select(func.count(MatchRegistration.id)).where(
                MatchRegistration.post_id == post_id,
                MatchRegistration.status == RegistrationStatus.approved,
            )
        )
        approved_count = approved_count_result.scalar() or 0
        if approved_count >= post.players_needed:
            post.status = MatchPostStatus.full

    return {"msg": "ok"}
