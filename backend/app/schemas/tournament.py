"""Typed tournament configuration and commands; all datetimes are UTC-naive internally."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator


def utc(value: datetime) -> datetime:
    return (
        value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    )


class TournamentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["knockout", "round_robin", "groups_knockout"] = "knockout"
    discipline: Literal["singles", "doubles", "mixed"] = "singles"
    group_count: int = Field(1, ge=1, le=16)
    courts: list[str] = Field(
        default_factory=lambda: ["1号场地"], min_length=1, max_length=16
    )
    match_minutes: int = Field(45, ge=5, le=300)
    third_place: bool = False
    allow_draw: bool = False
    max_parallel: int | None = Field(None, ge=1, le=16)
    qualifiers_per_group: int = Field(2, ge=1, le=8)
    approval_required: bool = False
    waitlist_enabled: bool = False
    ungrouped_display: bool = False

    @model_validator(mode="after")
    def consistent(self):
        self.courts = [s.strip() for s in self.courts]
        if any(not s or len(s) > 64 for s in self.courts) or len(
            set(self.courts)
        ) != len(self.courts):
            raise ValueError("场地名称必须非空且不重复（最多64字）")
        if self.format == "knockout" and self.allow_draw:
            raise ValueError("淘汰赛不能允许平局")
        if self.format == "groups_knockout" and self.group_count < 2:
            raise ValueError("循环接淘汰至少需要两个小组")
        return self


class TournamentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    club_id: int
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    sport_type: str = "网球"
    start_time: datetime
    end_time: datetime
    venue_id: int | None = None
    lock_venue: bool = False
    max_participants: int = Field(..., ge=2, le=128)
    entry_fee: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    images: list[str] = Field(default_factory=list, max_length=6)
    cover_image: str | None = None
    prize: str | None = Field(None, max_length=256)
    address: str = Field("", max_length=256)
    contact_name: str = Field("", max_length=64)
    contact_phone: str = Field("", max_length=20)
    auto_title: bool = False
    config: TournamentConfig | None = None
    registration_deadline: datetime | None = None
    cancellation_deadline: datetime | None = None

    @field_validator(
        "start_time", "end_time", "registration_deadline", "cancellation_deadline"
    )
    @classmethod
    def normalize(cls, value):
        return utc(value) if value else value

    @model_validator(mode="after")
    def validate_event(self):
        self.title = self.title.strip()
        self.address = self.address.strip()
        if not self.title:
            raise ValueError("请填写比赛名称")
        if not self.address and not self.venue_id:
            raise ValueError("请填写比赛地点或关联场地")
        if self.end_time <= self.start_time:
            raise ValueError("结束时间必须晚于开始时间")
        self.registration_deadline = self.registration_deadline or self.start_time
        self.cancellation_deadline = (
            self.cancellation_deadline or self.start_time - timedelta(hours=1)
        )
        if (
            self.registration_deadline > self.start_time
            or self.cancellation_deadline > self.start_time
        ):
            raise ValueError("截止时间不能晚于开赛时间")
        if self.config:
            teams = self.max_participants
            if self.config.discipline != "singles":
                if teams % 2:
                    raise ValueError("双打人数必须是偶数")
                teams //= 2
            if teams // self.config.group_count < 2:
                raise ValueError("每组至少需要两队")
            if (
                self.config.format == "groups_knockout"
                and teams // self.config.group_count < self.config.qualifiers_per_group
            ):
                raise ValueError("晋级队数不能超过每组队伍数")
        return self


class RegistrationCommand(BaseModel):
    requested_group: int = Field(0, ge=0, le=16)
    gender: Literal["male", "female"] | None = None
    pairing: Literal["random", "fixed"] = "random"


class ReasonCommand(BaseModel):
    reason: str = Field(min_length=1, max_length=256)


class ReviewCommand(ReasonCommand):
    approved: bool


class DrawCommand(BaseModel):
    archive_results: bool = False
    publish: bool = False
    expected_version: int = Field(0, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=64)
    reason: str = Field("", max_length=256)
    stage: Literal["initial", "knockout"] = "initial"


class VersionCommand(BaseModel):
    expected_version: int = Field(ge=1)


class ResultCommand(VersionCommand):
    winner_id: int | None = None
    score: str = Field("", max_length=128)
    is_draw: bool = False
    walkover: bool = False
    reason: str = Field("", max_length=256)


class ScheduleCommand(VersionCommand):
    court: str
    start_time: datetime

    @field_validator("start_time")
    @classmethod
    def normalize(cls, value):
        return utc(value)


class TieCommand(VersionCommand, ReasonCommand):
    group_no: int = Field(ge=1)
    team_ids: list[int] = Field(min_length=2)
