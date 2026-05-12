from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import (
    User, Club, MatchPost, MatchRegistration, MatchPostStatus,
    RegistrationStatus, Notification, NotificationType,
)
from app.schemas.schemas import (
    PostCreate, PostBrief, PostDetail, PostListParams, PaginatedResponse,
    RegisterPostRequest, ReviewRegistrationRequest, RegistrationBrief,
)

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=PaginatedResponse)
async def list_posts(
    club_id: int = Query(None),
    sport: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MatchPost, User.nickname, User.avatar_url, Club.name,
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

    query = query.group_by(MatchPost.id).order_by(MatchPost.created_at.desc())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for row in rows:
        post, nickname, avatar, club_name, reg_count = row
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
            user_nickname=nickname, user_avatar=avatar,
            club_name=club_name, registration_count=reg_count or 0,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=PostBrief)
async def create_post(
    req: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
        user_nickname=user.nickname, user_avatar=user.avatar_url,
        club_name=club.name if club else None,
        registration_count=0,
    )


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MatchPost, User.nickname, User.avatar_url, Club.name,
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
    post, nickname, avatar, club_name, reg_count = row

    # Get registrations
    reg_result = await db.execute(
        select(MatchRegistration, User.nickname, User.avatar_url)
        .join(User, MatchRegistration.user_id == User.id)
        .where(MatchRegistration.post_id == post_id)
        .order_by(MatchRegistration.id)
    )
    reg_rows = reg_result.all()

    registrations = []
    for r, r_nick, r_av in reg_rows:
        registrations.append(RegistrationBrief(
            id=r.id, user_id=r.user_id, message=r.message, status=r.status.value,
            user_nickname=r_nick, user_avatar=r_av,
        ))

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
        user_nickname=nickname, user_avatar=avatar,
        club_name=club_name, registration_count=reg_count or 0,
        notes=post.notes, venue_id=post.venue_id, booking_id=post.booking_id,
        registrations=registrations,
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
    if post.status != MatchPostStatus.open:
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
    if post.user_id != current_user.id:
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

    reg.status = RegistrationStatus(req.status)
    return {"msg": "ok"}
