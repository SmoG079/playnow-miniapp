from sqlalchemy import select
from app.models.models import User, ClubMember


async def can_view_club_documents(db, club, viewer):
    if not isinstance(viewer, User):
        return False
    if (
        viewer.id == club.created_by
        or str(getattr(viewer.role, "value", viewer.role)) == "platform_admin"
    ):
        return True
    return bool(
        await db.scalar(
            select(ClubMember.id).where(
                ClubMember.club_id == club.id, ClubMember.user_id == viewer.id
            )
        )
    )


async def validate_certification_documents(db, documents, viewer, previous=None):
    from urllib.parse import urlsplit
    from fastapi import HTTPException
    from app.core.config import get_settings
    from app.models.models import PrivateUpload

    origin = urlsplit(get_settings().PUBLIC_BASE_URL)
    previous_urls = {d.get("url") for d in previous or []}
    for document in documents or []:
        url = document.get("url", "")
        if url in previous_urls:
            continue  # Retain existing references until their explicit storage migration.
        parsed = urlsplit(url)
        prefix = "/api/v1/media/doc/"
        if (
            parsed.scheme != origin.scheme
            or parsed.netloc != origin.netloc
            or not parsed.path.startswith(prefix)
            or parsed.query
            or parsed.fragment
        ):
            raise HTTPException(422, "认证材料须通过私有上传接口上传")
        filename = parsed.path[len(prefix) :]
        record = await db.get(PrivateUpload, filename)
        if not record or record.user_id != viewer.id:
            raise HTTPException(403, "认证材料不属于当前申请人")
