"""Real persistence, authenticated HTTP boundaries and NTRP-only questionnaire results."""
from decimal import Decimal
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError
from tests.test_post_booking_permissions import db  # noqa: F401
from app.api.v1 import users
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import User
from app.schemas.schemas import RatingAssessmentRequest
from app.services.rating_assessment import VERSION, QUESTIONS, assess, catalog


def full(value=3):
    return {question["id"]: value for question in QUESTIONS}


@pytest.mark.parametrize("level", [2, 3, 4, 5])
def test_quick_grade_matches_selected_card(level):
    assert assess("quick", {"level": level}) == Decimal(level)


def test_full_questionnaire_rounds_skill_average_to_half_a_point():
    assert assess("full", full(0)) == Decimal("2.0")
    assert assess("full", full(7)) == Decimal("5.5")
    mixed = {question["id"]: index + 1 for index, question in enumerate(QUESTIONS)}
    assert assess("full", mixed) == Decimal("4.0")
    assert "utr" not in str(catalog()).lower()


@pytest.mark.parametrize("payload", [
    {"mode": "quick", "answers": {"level": 6}},
    {"mode": "quick", "answers": {"level": True}},
    {"mode": "quick", "answers": {"level": "3"}},
    {"mode": "quick", "answers": {"level": 3, "rally": 0}},
    {"mode": "full", "answers": {"rally": 0}},
    {"mode": "full", "answers": full(-1)},
    {"mode": "full", "answers": full(8)},
    {"mode": "full", "answers": {**full(), "unknown": 0}},
    {"mode": "quick", "answers": {"level": 3}, "utr_rating": 9},
    {"mode": "quick", "answers": {"level": 3}, "ntrp_level": 7},
    {"mode": "quick", "answers": {"level": 3}, "version": "future"},
])
def test_incomplete_unknown_and_client_scored_payloads_are_rejected(payload):
    with pytest.raises(ValidationError):
        RatingAssessmentRequest.model_validate({"version": VERSION, **payload})


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,answers,expected", [("quick", {"level": 4}, "4.0"), ("full", full(3), "3.5")])
async def test_http_assessment_persists_only_ntrp_and_answers(db, mode, answers, expected):
    user = await db.get(User, "1")
    app = FastAPI(); app.include_router(users.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/users/me/rating-assessment", json={"version": VERSION, "mode": mode, "answers": answers})
        assert response.status_code == 200, response.text
        assert response.json() == {"ntrp_level": float(expected), "rating_source": "self_assessment"}
        await db.refresh(user)
        assert user.ntrp_level == Decimal(expected)
        assert user.utr_rating is None
        assert user.rating_assessment == {"version": VERSION, "mode": mode, "answers": answers}
        assert user.rating_assessed_at is not None
        assert (await db.get(User, "2")).ntrp_level is None
        profile = await client.get("/api/v1/users/me")
        assert profile.status_code == 200
        assert Decimal(str(profile.json()["ntrp_level"])) == Decimal(expected)
        assert profile.json()["rating_source"] == "self_assessment"
        assert not {"utr_rating", "rating_assessment", "rating_assessed_at"} & profile.json().keys()


@pytest.mark.asyncio
async def test_reserved_utr_survives_assessment_and_manual_ntrp_changes(db):
    user = await db.get(User, "1"); user.utr_rating = Decimal("8.25")
    await db.commit()
    app = FastAPI(); app.include_router(users.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/users/me/rating-assessment", json={"version": VERSION, "mode": "quick", "answers": {"level": 3}})
        assert response.status_code == 200
        await db.refresh(user); assessment = user.rating_assessment
        assert user.utr_rating == Decimal("8.25")
        response = await client.put("/api/v1/users/me", json={"nickname": "保留资料", "ntrp_level": 3})
        assert response.status_code == 200
        await db.refresh(user); assert user.rating_assessment == assessment
        response = await client.put("/api/v1/users/me", json={"ntrp_level": 4.5})
        assert response.status_code == 200
        await db.refresh(user)
        assert user.ntrp_level == Decimal("4.5") and user.utr_rating == Decimal("8.25")
        assert user.rating_assessment is None and user.rating_assessed_at is None


@pytest.mark.asyncio
async def test_anonymous_and_invalid_answers_cannot_modify_profile(db):
    user = await db.get(User, "1")
    app = FastAPI(); app.include_router(users.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/users/me/rating-questionnaire")).status_code == 401
        assert (await client.post("/api/v1/users/me/rating-assessment", json={"version": VERSION, "mode": "quick", "answers": {"level": 3}})).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: user
        assert (await client.post("/api/v1/users/me/rating-assessment", json={"version": VERSION, "mode": "full", "answers": {"rally": 7}})).status_code == 422
        await db.refresh(user)
        assert user.ntrp_level is None and user.rating_assessment is None and user.utr_rating is None
