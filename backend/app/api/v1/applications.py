"""A paginated inbox with server-defined review ownership."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, literal, cast, String, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_platform_admin, _v
from app.core.database import get_db
from app.core.logger import get_logger
from app.models.models import (Club, ClubMember, ClubMemberRole, ClubStatus, User,
    MatchPost, MatchRegistration, Tournament, TournamentRegistration, TournamentAudit,
    Notification, NotificationType)
from app.schemas.schemas import PaginatedResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/applications", tags=["applications"])

class ClubReview(BaseModel):
    approved: bool
    reason: str = Field("", max_length=256)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value):
        return value.strip()

@router.get("", response_model=PaginatedResponse)
async def list_applications(
    scope: Literal["todo", "done", "mine"] = "todo",
    kind: Literal["all", "club", "post", "tournament"] = "all",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    queries = []
    # Each arm shares these columns; no private phone/payment fields leave the inbox.
    if kind in ("all", "club") and (scope == "mine" or _v(user.role) == "platform_admin"):
        q = select(literal("club").label("kind"), Club.id.label("target_id"),
            Club.id.label("application_id"), Club.name.label("title"),
            User.nickname.label("applicant"), User.avatar_url.label("avatar_url"),
            Club.approval_status.label("status"), Club.created_at.label("created_at"),
            Club.review_reason.label("reason"), Club.address.label("description"),
            Club.city.label("city"), Club.cover_image.label("cover_image")
        ).join(User, User.id == Club.created_by)
        if scope == "mine": q = q.where(Club.created_by == user.id)
        elif scope == "todo": q = q.where(Club.approval_status == "pending")
        else: q = q.where(Club.approval_status.in_(["approved", "rejected"]))
        queries.append(q)
    if scope != "mine" and kind in ("all", "post"):
        q = select(literal("post"), MatchPost.id, MatchRegistration.id, MatchPost.title,
            User.nickname, User.avatar_url, cast(MatchRegistration.status, String),
            MatchRegistration.created_at, MatchRegistration.review_reason, MatchRegistration.message,
            MatchPost.city, MatchPost.images[0].as_string()
        ).select_from(MatchRegistration).join(MatchPost, MatchPost.id == MatchRegistration.post_id).join(User, User.id == MatchRegistration.user_id).where(MatchPost.user_id == user.id)
        if scope == "todo": q = q.where(MatchRegistration.status == "pending", MatchPost.status != "closed")
        else: q = q.where(MatchRegistration.status.in_(["approved", "rejected"]), MatchPost.approval_required.is_(True))
        queries.append(q)
    if scope != "mine" and kind in ("all", "tournament"):
        created = select(TournamentAudit.tournament_id).where(TournamentAudit.actor_id == user.id, TournamentAudit.action == "created")
        q = select(literal("tournament"), Tournament.id, TournamentRegistration.id, Tournament.title,
            User.nickname, User.avatar_url, TournamentRegistration.approval,
            TournamentRegistration.created_at, TournamentRegistration.review_reason, literal(None, type_=String),
            Tournament.city, Tournament.cover_image
        ).select_from(TournamentRegistration).join(Tournament, Tournament.id == TournamentRegistration.tournament_id).join(User, User.id == TournamentRegistration.user_id).where(Tournament.id.in_(created))
        if scope == "todo": q = q.where(TournamentRegistration.approval == "pending", TournamentRegistration.admission == "review", Tournament.roster_frozen.is_(False), Tournament.status != "cancelled")
        else: q = q.where(TournamentRegistration.approval.in_(["approved", "rejected"]), Tournament.config["approval_required"].as_boolean().is_(True))
        queries.append(q)
    if not queries:
        return PaginatedResponse(items=[], total=0, page=page, page_size=page_size)
    names = "kind target_id application_id title applicant avatar_url status created_at reason description city cover_image".split()
    queries = [q.with_only_columns(*(column.label(name) for column, name in zip(q.selected_columns, names))) for q in queries]
    inbox = union_all(*queries).subquery()
    total = await db.scalar(select(func.count()).select_from(inbox)) or 0
    result = await db.execute(select(inbox).order_by(inbox.c.created_at.desc(), inbox.c.kind, inbox.c.application_id.desc()).offset((page-1)*page_size).limit(page_size))
    items = [dict(row) for row in result.mappings()]
    for item in items:
        item["can_review"] = scope == "todo"
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)

@router.post("/clubs/{club_id}/review")
async def review_club(club_id: int, req: ClubReview,
    user: User = Depends(get_platform_admin), db: AsyncSession = Depends(get_db)):
    # This check also protects calls outside FastAPI's dependency resolution.
    if _v(user.role) != "platform_admin": raise HTTPException(403, "只有系统管理员可以审核俱乐部")
    club = (await db.execute(select(Club).where(Club.id == club_id).with_for_update())).scalar_one_or_none()
    if not club: raise HTTPException(404, "俱乐部不存在")
    if club.approval_status != "pending": raise HTTPException(409, "申请已处理，请刷新列表")
    if not req.approved and not req.reason: raise HTTPException(422, "请填写拒绝原因")
    creator = (await db.execute(select(User).where(User.id == club.created_by).with_for_update())).scalar_one_or_none()
    if not creator: raise HTTPException(409, "申请人不存在")
    club.approval_status = "approved" if req.approved else "rejected"
    club.status = ClubStatus.active if req.approved else ClubStatus.inactive
    club.review_reason = req.reason or None
    club.reviewed_by = user.id; club.reviewed_at = datetime.utcnow()
    if req.approved:
        member = await db.scalar(select(ClubMember).where(ClubMember.club_id == club.id, ClubMember.user_id == creator.id))
        if not member: db.add(ClubMember(club_id=club.id, user_id=creator.id, role=ClubMemberRole.owner))
        if _v(creator.role) == "user": creator.role = "club_admin"
    db.add(Notification(user_id=creator.id, type=NotificationType.system,
        title="俱乐部申请已通过" if req.approved else "俱乐部申请未通过",
        content=f"《{club.name}》" + ("已通过审核，可以管理俱乐部和创建场地。" if req.approved else f"未通过审核：{req.reason}"),
        ref_type="club_application", ref_id=club.id))
    await db.flush()
    logger.info("club application reviewed: club=%s result=%s", club.id, club.approval_status)
    return {"status": club.approval_status}

@router.post("/{kind}/{application_id}/review")
async def review_application(kind: Literal["post", "tournament"], application_id: int,
    req: ClubReview, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not req.approved and not req.reason: raise HTTPException(422, "请填写拒绝原因")
    if kind == "post":
        from app.api.v1.posts import review_registration
        from app.schemas.schemas import ReviewRegistrationRequest
        registration = await db.get(MatchRegistration, application_id)
        if not registration: raise HTTPException(404, "报名不存在")
        return await review_registration(registration.post_id, registration.user_id,
            ReviewRegistrationRequest(status="approved" if req.approved else "rejected", reason=req.reason), user, db)
    from app.api.v1.tournaments import review
    from app.schemas.tournament import ReviewCommand
    registration = await db.get(TournamentRegistration, application_id)
    if not registration: raise HTTPException(404, "报名不存在")
    return await review(registration.tournament_id, application_id,
        ReviewCommand(approved=req.approved, reason=req.reason or "审核通过"), user, db)
