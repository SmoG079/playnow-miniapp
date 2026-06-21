import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, delete
from math import radians, cos, sin, asin, sqrt
from app.core.database import get_db
from app.api.deps import get_current_user, _v
from app.models.models import (
    User, Club, ClubMember, Venue, MatchPost, MatchRegistration, MatchPostStatus,
    RegistrationStatus, Notification, NotificationType, Comment,
)
from app.schemas.schemas import (
    PostCreate, PostUpdate, PostBrief, PostDetail, PostListParams, PaginatedResponse,
    RegisterPostRequest, ReviewRegistrationRequest, RegistrationBrief,
    CommentCreate, CommentBrief,
)

router = APIRouter(prefix="/posts", tags=["posts"])


def _parse_ntrp_level(level_str: str) -> float:
    """Parse NTRP level string like '2.0' or '2.5' to float."""
    try:
        return float(level_str.strip())
    except (ValueError, AttributeError):
        return 0.0


def _level_matches(selected_levels: list[str], level_required: str | None) -> bool:
    """Check if a post's level_required matches selected NTRP levels.

    level_required can be:
    - None or empty: matches if '不限' is selected, otherwise no match
    - Single level: '2.5'
    - Range: '2.0-2.5'
    """
    if not level_required:
        # Posts without a level requirement match only if '不限' is explicitly selected
        return False

    selected_values = sorted(_parse_ntrp_level(l) for l in selected_levels if l.strip())
    if not selected_values:
        return False

    level_required = level_required.strip()
    if '-' in level_required:
        # Range format: "2.0-2.5"
        parts = level_required.split('-', 1)
        req_min = _parse_ntrp_level(parts[0])
        req_max = _parse_ntrp_level(parts[1])
        if req_min == 0.0 and req_max == 0.0:
            return False
        # Match if any selected level falls within the required range
        for sel in selected_values:
            if req_min <= sel <= req_max:
                return True
        return False
    else:
        # Single level format: "2.5"
        req_value = _parse_ntrp_level(level_required)
        if req_value == 0.0:
            return False
        return any(abs(sel - req_value) < 1e-6 for sel in selected_values)


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
    ntrp_levels: str = Query(None),
    lat: float = Query(None),
    lng: float = Query(None),
    sort_by: str = Query('created', regex='^(created|distance)$'),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    approved_count = func.sum(
        case((MatchRegistration.status == RegistrationStatus.approved, 1), else_=0)
    )
    pending_count = func.sum(
        case((MatchRegistration.status == RegistrationStatus.pending, 1), else_=0)
    )
    query = (
        select(MatchPost, User.nickname, User.avatar_url, User.phone, Club.name,
               Club.latitude, Club.longitude,
               approved_count, pending_count)
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

    selected_levels = [l for l in (ntrp_levels or '').split(',') if l.strip()] if ntrp_levels else []
    if selected_levels:
        all_posts = select(MatchPost).where(MatchPost.id > 0)
        if club_id:
            all_posts = all_posts.where(MatchPost.club_id == club_id)
        if sport:
            all_posts = all_posts.where(MatchPost.sport_type == sport)
        if status:
            all_posts = all_posts.where(MatchPost.status == status)
        result_all = await db.execute(all_posts)
        matched_ids = [p.id for p in result_all.scalars().all() if _level_matches(selected_levels, p.level_required)]
        if matched_ids:
            query = query.where(MatchPost.id.in_(matched_ids))
            count_query = count_query.where(MatchPost.id.in_(matched_ids))
        else:
            query = query.where(False)
            count_query = count_query.where(False)

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
        post, nickname, avatar, phone, club_name, club_lat, club_lng, approved_cnt, pending_cnt = row
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
            approval_required=post.approval_required,
            created_at=post.created_at,
            user_nickname=user_nickname, user_avatar=avatar,
            club_name=club_name, registration_count=approved_cnt or 0,
            pending_count=pending_cnt or 0,
            distance=distance,
            price=post.price,
            venue_id=post.venue_id,
            booking_id=post.booking_id,
            images=post.images,
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
    # 定场约球 requires club admin; 自由约球 allows any user
    if req.club_id:
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

    if req.preferred_start and req.preferred_end and req.preferred_end <= req.preferred_start:
        raise HTTPException(status_code=422, detail="结束时间必须晚于开始时间")

    sport_type = req.sport_type
    if req.venue_id and not sport_type:
        venue_result = await db.execute(select(Venue).where(Venue.id == req.venue_id))
        venue = venue_result.scalar_one_or_none()
        if venue:
            sport_type = venue.sport_type

    post = MatchPost(
        club_id=req.club_id,
        user_id=current_user.id,
        title=req.title,
        sport_type=sport_type,
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
        images=req.images,
        approval_required=req.approval_required,
        price=req.price,
    )
    db.add(post)
    await db.flush()
    await db.refresh(post)

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    club = None
    if req.club_id:
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
        approval_required=post.approval_required,
        created_at=post.created_at,
        user_nickname=user.nickname or _fallback_nickname(user.id, user.phone),
        user_avatar=user.avatar_url,
        club_name=club.name if club else None,
        registration_count=0,
        pending_count=0,
        price=post.price,
    )


@router.put("/{post_id}", response_model=PostBrief)
async def update_post(
    post_id: int,
    req: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id and _v(current_user.role) != "platform_admin":
        raise HTTPException(status_code=403, detail="Only post owner can update")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(post, key, value)

    await db.flush()
    await db.refresh(post)

    user_result = await db.execute(select(User).where(User.id == post.user_id))
    user = user_result.scalar_one()
    club_result = await db.execute(select(Club).where(Club.id == post.club_id))
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
        approval_required=post.approval_required,
        created_at=post.created_at,
        user_nickname=user.nickname or _fallback_nickname(user.id, user.phone),
        user_avatar=user.avatar_url,
        club_name=club.name if club else None,
        registration_count=0,
        price=post.price,
        images=post.images,
    )


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    approved_count = func.sum(
        case((MatchRegistration.status == RegistrationStatus.approved, 1), else_=0)
    )
    pending_count = func.sum(
        case((MatchRegistration.status == RegistrationStatus.pending, 1), else_=0)
    )
    result = await db.execute(
        select(MatchPost, User.nickname, User.avatar_url, User.phone, Club.name,
               approved_count, pending_count)
        .join(User, MatchPost.user_id == User.id)
        .join(Club, MatchPost.club_id == Club.id)
        .outerjoin(MatchRegistration, MatchRegistration.post_id == MatchPost.id)
        .where(MatchPost.id == post_id)
        .group_by(MatchPost.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    post, nickname, avatar, phone, club_name, approved_cnt, pending_cnt = row

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
        approval_required=post.approval_required,
        created_at=post.created_at,
        user_nickname=nickname or _fallback_nickname(post.user_id, phone), user_avatar=avatar,
        club_name=club_name, registration_count=approved_cnt or 0,
        pending_count=pending_cnt or 0,
        notes=post.notes, description=post.description, documents=post.documents,
        venue_id=post.venue_id, booking_id=post.booking_id,
        registrations=registrations,
        price=post.price, user_phone=user_phone, venue_address=venue_address,
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
        status=RegistrationStatus.pending if post.approval_required else RegistrationStatus.approved,
    )
    db.add(reg)

    # Notify post owner
    action_text = "报名了你的约球帖" if not post.approval_required else "报名了你的约球帖，等待审核"
    notif = Notification(
        user_id=post.user_id,
        type=NotificationType.match,
        title="有人报名了你的约球帖" if not post.approval_required else "有人报名待审核",
        content=f"用户 {current_user.nickname or '新用户'} {action_text}《{post.title}》",
        ref_id=post.id,
        ref_type="match_post",
    )
    db.add(notif)

    # If no approval required and now full, mark post as full
    if not post.approval_required:
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


@router.get("/{post_id}/comments")
async def list_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    # Verify post exists
    post_result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    if not post_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Post not found")

    # Top-level comments
    result = await db.execute(
        select(Comment, User.nickname, User.avatar_url)
        .join(User, Comment.user_id == User.id)
        .where(
            Comment.post_id == post_id,
            Comment.parent_id.is_(None),
        )
        .order_by(Comment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()

    items = []
    for comment, nickname, avatar in rows:
        # Fetch up to 3 recent replies
        reply_result = await db.execute(
            select(Comment, User.nickname, User.avatar_url)
            .join(User, Comment.user_id == User.id)
            .where(
                Comment.parent_id == comment.id,
            )
            .order_by(Comment.created_at.asc())
            .limit(3)
        )
        reply_rows = reply_result.all()
        replies = []
        for r, r_nick, r_avatar in reply_rows:
            replies.append(_comment_to_brief(r, r_nick, r_avatar))

        # Count total replies
        count_result = await db.execute(
            select(func.count(Comment.id)).where(
                Comment.parent_id == comment.id,
            )
        )
        reply_count = count_result.scalar() or 0

        brief = _comment_to_brief(comment, nickname, avatar)
        brief.reply_count = reply_count
        brief.replies = replies
        items.append(brief)

    return PaginatedResponse(items=items, total=len(items), page=page, page_size=page_size)


@router.post("/{post_id}/comments")
async def create_comment(
    post_id: int,
    req: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if req.parent_id:
        parent_result = await db.execute(
            select(Comment).where(
                Comment.id == req.parent_id,
                Comment.post_id == post_id,
                Comment.parent_id.is_(None),  # only reply to top-level comments
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid parent comment")

    comment = Comment(
        post_id=post_id,
        user_id=current_user.id,
        parent_id=req.parent_id,
        content=req.content,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)

    # Notify post owner
    if current_user.id != post.user_id:
        notif = Notification(
            user_id=post.user_id,
            type=NotificationType.match,
            title="你的约球帖有新评论",
            content=f"用户 {current_user.nickname or '新用户'} 评论了《{post.title}》",
            ref_id=post.id,
            ref_type="match_post",
        )
        db.add(notif)

    # Notify parent comment author if replying
    if req.parent_id:
        parent_comment_result = await db.execute(
            select(Comment).where(Comment.id == req.parent_id)
        )
        parent_comment = parent_comment_result.scalar_one_or_none()
        if parent_comment and parent_comment.user_id != current_user.id:
            reply_notif = Notification(
                user_id=parent_comment.user_id,
                type=NotificationType.match,
                title="有人回复了你的评论",
                content=f"用户 {current_user.nickname or '新用户'} 回复了你的评论",
                ref_id=post.id,
                ref_type="match_post",
            )
            db.add(reply_notif)

    return _comment_to_brief(comment, current_user.nickname, current_user.avatar_url)


@router.delete("/{post_id}")
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.user_id != current_user.id and _v(current_user.role) != "platform_admin":
        raise HTTPException(status_code=403, detail="Only post owner can delete")
    # Delete related data
    await db.execute(delete(MatchRegistration).where(MatchRegistration.post_id == post_id))
    await db.execute(delete(Comment).where(Comment.post_id == post_id))
    await db.delete(post)
    return {"msg": "ok"}


@router.delete("/{post_id}/comments/{comment_id}")
async def delete_comment(
    post_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_result = await db.execute(select(MatchPost).where(MatchPost.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment_result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.post_id == post_id)
    )
    comment = comment_result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    role = _v(current_user.role)
    if comment.user_id != current_user.id and post.user_id != current_user.id and role != "platform_admin":
        raise HTTPException(status_code=403, detail="No permission to delete this comment")

    comment.is_deleted = True
    return {"msg": "ok"}


def _comment_to_brief(comment: Comment, nickname: str | None, avatar: str | None) -> CommentBrief:
    display_content = comment.content if not comment.is_deleted else "该评论已删除"
    return CommentBrief(
        id=comment.id,
        post_id=comment.post_id,
        user_id=comment.user_id,
        user_nickname=nickname or _fallback_nickname(comment.user_id, None),
        user_avatar=avatar,
        content=display_content,
        parent_id=comment.parent_id,
        is_deleted=comment.is_deleted,
        created_at=comment.created_at,
    )
