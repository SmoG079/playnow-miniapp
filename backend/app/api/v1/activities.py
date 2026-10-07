from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_optional_user
from app.models.models import Activity, User
from app.api.v1.posts import get_post
from app.api.v1.tournaments import get_tournament

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("/{activity_id}")
async def get_activity(
    activity_id: int,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    activity = await db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(404, "活动不存在")
    detail = (await get_post(activity_id, db) if activity.kind == "post"
              else await get_tournament(activity_id, user, db))
    return {"activity_id": activity.id, "kind": activity.kind, "detail": detail}
