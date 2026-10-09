from datetime import datetime, date, time
from typing import Optional, Any, List, Annotated, Literal
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, field_validator, computed_field, model_validator, StrictInt, StrictFloat, ConfigDict
from decimal import Decimal
from app.services.public_identity import public_user_id


def _parse_flexible_time(value: Any) -> Any:
    """Accept 'HH:MM' or 'HH:MM:SS' strings for time fields."""
    if isinstance(value, str):
        if len(value) == 5:
            return f"{value}:00"
    return value


FlexibleTime = Annotated[time, BeforeValidator(_parse_flexible_time)]
DecimalAsFloat = Annotated[
    Decimal,
    PlainSerializer(lambda v: float(v) if v is not None else None, return_type=float, when_used="json"),
]


PublicUserID = Annotated[str, PlainSerializer(public_user_id, return_type=str, when_used="json")]


# ── Auth ──

class WxLoginRequest(BaseModel):
    code: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class PhoneRequest(BaseModel):
    code: str  # WeChat phone number encrypted data code


# ── User ──

class UserProfile(BaseModel):
    id: PublicUserID
    nickname: Optional[str]
    avatar_url: Optional[str]
    phone: Optional[str]
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=64)
    avatar_url: Optional[str] = Field(None, max_length=512)
    phone: Optional[str] = Field(None, max_length=20)
    ntrp_level: Optional[Decimal] = Field(None, ge=1.0, le=7.0)

class UserMeResponse(UserProfile):
    roles: list[str] = Field(default_factory=list)
    managed_club_ids: list[int] = []
    ntrp_level: Optional[Decimal] = None
    rating_source: Optional[str] = None


class RatingAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["playnow_self_v2"]
    mode: Literal["quick", "full"]
    answers: dict[str, StrictInt | StrictFloat] = Field(..., min_length=1, max_length=6)

    @model_validator(mode="after")
    def complete_answers(self):
        from app.services.rating_assessment import validate_answers
        validate_answers(self.mode, self.answers)
        return self


class RatingAssessmentResponse(BaseModel):
    ntrp_level: DecimalAsFloat
    rating_source: Literal["self_assessment"] = "self_assessment"


# ── Club ──

class ClubCreate(BaseModel):
    city: Optional[str] = Field(None, min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    sport_types: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    rules: Optional[str] = None
    cover_image: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    documents: list[dict] = Field(default_factory=list)  # [{name, url, size}]
    address: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    contact_phone: str = Field(..., min_length=1, max_length=20)
    opening_time: Optional[str] = "08:00"
    closing_time: Optional[str] = "22:00"

    @field_validator("city")
    @classmethod
    def normalized_city(cls, value):
        if value is None: return None
        value=value.strip()
        if not value: raise ValueError("请选择活动所在城市")
        return value


class ClubUpdate(BaseModel):
    city: Optional[str] = Field(None, min_length=1, max_length=64)
    name: Optional[str] = None
    sport_types: Optional[list[str]] = None
    description: Optional[str] = None
    rules: Optional[str] = None
    cover_image: Optional[str] = None
    images: Optional[list[str]] = None
    documents: Optional[list[dict]] = None
    address: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    contact_phone: Optional[str] = None
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None

    @field_validator("city")
    @classmethod
    def normalized_city(cls, value):
        if value is None: return None
        value=value.strip()
        if not value: raise ValueError("请选择活动所在城市")
        return value


class ClubBrief(BaseModel):
    approval_status: str = "approved"
    review_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    city: Optional[str] = Field(None, min_length=1, max_length=64)
    id: int
    name: str
    sport_types: Any
    cover_image: Optional[str]
    address: Optional[str]
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    status: str
    view_count: int = 0
    exposure_count: int = 0
    distance: Optional[float] = None
    nearest_venue_id: Optional[int] = None
    nearest_venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    venue_city: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None

    @field_validator("opening_time", "closing_time", mode="before")
    @classmethod
    def _coerce_time(cls, v):
        if v is None: return None
        if isinstance(v, time): return v.strftime("%H:%M")
        return v

    class Config:
        from_attributes = True

class ClubDetail(ClubBrief):
    description: Optional[str]
    rules: Optional[str]
    images: Any
    documents: Any
    contact_phone: Optional[str]
    venues: list["VenueBrief"] = []
    created_at: datetime

    class Config:
        from_attributes = True

class GeocodeRequest(BaseModel):
    address: str


class GeocodeResponse(BaseModel):
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ClubListParams(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    sport: Optional[str] = None
    keyword: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# ── Venue ──

class VenueLocation(BaseModel):
    city: Optional[str] = Field(None, max_length=64)
    address: Optional[str] = Field(None, max_length=256)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    @field_validator("city", "address")
    @classmethod
    def clean_location(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("城市和地址不能留空")
        return value

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("经纬度必须同时填写")
        return self

class VenuePriceRules(BaseModel):
    @field_validator("price_rules", check_fields=False)
    @classmethod
    def validate_price_rules(cls, rules):
        if rules is None:
            return rules
        for rule in rules:
            if rule.get("type") not in ("date_range", "daily_time", "time_range"):
                raise ValueError("不支持的价格规则类型")
            try:
                price = Decimal(str(rule["price"]))
                if not price.is_finite() or price < 0 or price > Decimal("99999999.99") or price.as_tuple().exponent < -2:
                    raise ValueError()
                start, end = rule.get("start_time"), rule.get("end_time")
                if start: time.fromisoformat(start)
                if end: time.fromisoformat(end)
                if start and end and time.fromisoformat(start) >= time.fromisoformat(end):
                    raise ValueError()
                if rule["type"] != "date_range" and (not start or not end):
                    raise ValueError()
                if rule["type"] == "date_range":
                    if date.fromisoformat(rule["start_date"]) > date.fromisoformat(rule["end_date"]):
                        raise ValueError()
                # Normalize strings for lexicographic pricing comparisons.
                if start: rule["start_time"] = time.fromisoformat(start).strftime("%H:%M")
                if end: rule["end_time"] = time.fromisoformat(end).strftime("%H:%M")
            except (ValueError, TypeError, KeyError, ArithmeticError):
                raise ValueError("价格规则需包含有效日期/时段及非负有限价格")
        return rules


class VenueCreate(VenueLocation, VenuePriceRules):
    name: str = Field(..., min_length=1, max_length=64)
    sport_type: str = "tennis"
    price_per_hour: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    max_capacity: int = Field(default=4, ge=1)
    cover_image: Optional[str] = None
    sort_order: int = 0
    price_rules: Optional[list[dict]] = None

class VenueUpdate(VenueLocation, VenuePriceRules):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    sport_type: Optional[str] = Field(None, min_length=1, max_length=32)
    price_per_hour: Optional[Decimal] = Field(None, gt=0, max_digits=10, decimal_places=2)
    max_capacity: Optional[int] = Field(None, ge=1)
    cover_image: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[Literal["active", "maintenance", "closed"]] = None
    price_rules: Optional[list[dict]] = None

    @model_validator(mode="after")
    def preserve_required_fields(self):
        for name in ("name", "sport_type", "price_per_hour", "max_capacity", "sort_order", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError("场地必填字段不可清空")
        return self

class VenueBrief(VenueLocation):
    id: int
    club_id: int
    name: str
    sport_type: str
    price_per_hour: Decimal
    max_capacity: int
    cover_image: Optional[str]
    status: str
    price_rules: Optional[list[dict]] = None

    class Config:
        from_attributes = True

class VenueDetail(VenueBrief):
    created_at: datetime

    class Config:
        from_attributes = True


# ── Time Slot ──

class SlotPriceRule(BaseModel):
    start_time: FlexibleTime
    end_time: FlexibleTime
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class SlotGenerateRequest(BaseModel):
    date_from: date
    date_to: date
    start_time: FlexibleTime = time(8, 0)
    end_time: FlexibleTime = time(22, 0)
    interval_minutes: Literal[30] = 30
    price_rules: list[SlotPriceRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.date_to < self.date_from or (self.date_to - self.date_from).days > 30:
            raise ValueError("排期日期范围须为 1 至 31 天")
        if self.start_time >= self.end_time:
            raise ValueError("排期结束时间必须晚于开始时间")
        for value in (self.start_time, self.end_time):
            if value.second or value.microsecond or value.minute % 30:
                raise ValueError("排期须对齐 30 分钟边界")
        if any(rule.start_time >= rule.end_time for rule in self.price_rules):
            raise ValueError("价格规则结束时间必须晚于开始时间")
        return self


class SlotBrief(BaseModel):
    id: int
    venue_id: int
    date: date
    start_time: time
    end_time: time
    price: Decimal  # effective price (override or venue default)
    status: str

    class Config:
        from_attributes = True

class SlotDateGroup(BaseModel):
    date: date
    slots: list[SlotBrief]


class CourtSlotCell(BaseModel):
    slot_id: int
    venue_id: int
    start_time: time
    end_time: time
    price: Decimal
    status: str  # available / locked / booked / maintenance


class CourtSlotRow(BaseModel):
    time_label: str  # e.g. "07:00"
    cells: list[CourtSlotCell]


class VenueSlotGridResponse(BaseModel):
    club: dict
    venues: list[dict]
    rows: list[CourtSlotRow]


class SlotStatusUpdateRequest(BaseModel):
    status: str = Field(..., pattern='^(available|maintenance)$')


# ── Booking ──

class BookingCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    slot_ids: list[int] = Field(min_length=2, max_length=48)

    def resolved_slot_ids(self) -> list[int]:
        return self.slot_ids

class BookingDetail(BaseModel):
    id: int
    order_no: str
    user_id: PublicUserID
    venue_id: int
    slot_id: int
    slot_ids: Optional[list[int]] = None
    club_id: int
    amount: Decimal
    status: str
    payment_time: Optional[datetime]
    wx_transaction_id: Optional[str]
    prepay_id: Optional[str] = None
    prepay_id_created_at: Optional[datetime] = None
    cancel_reason: Optional[str]
    cancel_time: Optional[datetime]
    created_at: datetime
    venue_name: Optional[str] = None
    club_name: Optional[str] = None
    slot_date: Optional[date] = None
    slot_start: Optional[time] = None
    slot_end: Optional[time] = None
    slot_datetime: Optional[str] = None
    refund_amount: Optional[Decimal] = None
    refund_id: Optional[str] = None
    refund_time: Optional[datetime] = None
    refund_status: Optional[str] = None

    class Config:
        from_attributes = True

class BookingListParams(BaseModel):
    status: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)

class PayRequest(BaseModel):
    booking_id: int

class PayResponse(BaseModel):
    """Return params for wx.requestPayment"""
    timeStamp: str
    nonceStr: str
    package: str
    signType: str
    paySign: str

class CancelRequest(BaseModel):
    reason: Optional[str] = None


class RefundRequest(BaseModel):
    reason: Optional[str] = None
    amount: Optional[Decimal] = None  # 部分退款金额，不填则全额退款

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


# ── Match Post ──

class PostCreate(BaseModel):
    address: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, min_length=1, max_length=64)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    club_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=256)
    sport_type: Optional[str] = None
    preferred_date: date
    preferred_start: time
    preferred_end: time
    players_needed: int = Field(..., ge=1)
    price: Decimal = Field(..., ge=Decimal("0.00"))
    level_required: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    documents: Optional[list[dict]] = None
    venue_id: Optional[int] = None
    booking_id: Optional[int] = None
    approval_required: bool = False
    images: Optional[list[str]] = None

    @model_validator(mode="after")
    def required_information(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("活动地点经纬度须同时填写")
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("请填写活动名称")
        if self.preferred_end <= self.preferred_start:
            raise ValueError("结束时间必须晚于开始时间")
        return self

    @field_validator("city")
    @classmethod
    def normalized_city(cls, value):
        if value is None: return None
        value=value.strip()
        if not value: raise ValueError("请选择活动所在城市")
        return value


class PostUpdate(BaseModel):
    address: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, min_length=1, max_length=64)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    title: Optional[str] = Field(None, max_length=256)
    sport_type: Optional[str] = None
    preferred_date: Optional[date] = None
    preferred_start: Optional[time] = None
    preferred_end: Optional[time] = None
    players_needed: Optional[int] = Field(default=None, ge=1)
    price: Optional[Decimal] = Field(None, ge=0)
    status: Optional[Literal["open", "closed", "full"]] = None
    level_required: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    documents: Optional[list[dict]] = None
    venue_id: Optional[int] = None
    booking_id: Optional[int] = None
    approval_required: Optional[bool] = None

    @model_validator(mode="after")
    def preserve_required_information(self):
        for field in ("title", "preferred_date", "preferred_start", "preferred_end", "players_needed", "status", "approval_required"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("活动名称、时间和人数不可清空")
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("请填写活动名称")
        return self

    @field_validator("city")
    @classmethod
    def normalized_city(cls, value):
        if value is None: return None
        value=value.strip()
        if not value: raise ValueError("请选择活动所在城市")
        return value


class PostBrief(BaseModel):
    address: Optional[str] = Field(None, max_length=256)
    city: Optional[str] = Field(None, min_length=1, max_length=64)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    @computed_field
    @property
    def activity_id(self) -> int:
        return self.id

    notes: Optional[str] = None
    id: int
    club_id: Optional[int] = None
    user_id: PublicUserID
    title: str
    sport_type: Optional[str]
    preferred_date: Optional[date]
    preferred_start: Optional[time]
    preferred_end: Optional[time]
    players_needed: int
    price: Optional[DecimalAsFloat] = None
    level_required: Optional[str]
    status: str
    approval_required: bool = False
    created_at: datetime
    user_nickname: Optional[str] = None
    user_avatar: Optional[str] = None
    club_name: Optional[str] = None
    registration_count: int = 0
    pending_count: int = 0
    distance: Optional[float] = None  # km
    venue_id: Optional[int] = None
    booking_id: Optional[int] = None
    images: Optional[list[str]] = None

    class Config:
        from_attributes = True

class MyPostRegistration(BaseModel):
    id: int
    activity_id: int
    post_id: int
    user_id: PublicUserID
    status: str
    message: Optional[str] = None
    created_at: datetime
    post_title: str
    post_status: str
    preferred_date: Optional[date] = None
    preferred_start: Optional[time] = None
    preferred_end: Optional[time] = None
    club_id: Optional[int] = None
    club_name: Optional[str] = None


class PostDetail(PostBrief):
    venue_name: Optional[str] = None
    notes: Optional[str]
    description: Optional[str] = None
    documents: Optional[list[dict]] = None
    venue_id: Optional[int]
    booking_id: Optional[int]
    registrations: list["RegistrationBrief"] = []
    user_phone: Optional[str] = None
    venue_address: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    cover_image: Optional[str] = None
    club_documents: Optional[list[dict]] = None

    class Config:
        from_attributes = True

class RegistrationBrief(BaseModel):
    id: int
    user_id: PublicUserID
    message: Optional[str]
    status: str
    user_nickname: Optional[str] = None
    user_avatar: Optional[str] = None

    class Config:
        from_attributes = True

class PostListParams(BaseModel):
    club_id: Optional[int] = None
    sport: Optional[str] = None
    status: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    sort_by: Optional[str] = Field(default='created', pattern='^(created|distance)$')
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)

class RegisterPostRequest(BaseModel):
    message: Optional[str] = None

class ReviewRegistrationRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=256)
    status: str  # approved / rejected


# ── Comment ──

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=512)
    parent_id: Optional[int] = None

class CommentBrief(BaseModel):
    id: int
    post_id: int
    user_id: PublicUserID
    user_nickname: Optional[str] = None
    user_avatar: Optional[str] = None
    content: str
    parent_id: Optional[int] = None
    is_deleted: bool = False
    created_at: datetime
    reply_count: int = 0
    replies: list["CommentBrief"] = []

    class Config:
        from_attributes = True


# ── Tournament ──

class TournamentCreate(BaseModel):
    club_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    sport_type: Optional[str] = None
    start_time: datetime
    end_time: datetime
    venue_id: Optional[int] = None
    lock_venue: bool = False
    max_participants: Optional[int] = None
    entry_fee: Decimal = Decimal("0")
    images: Optional[list[str]] = None
    cover_image: Optional[str] = None
    prize: Optional[str] = None

class TournamentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    sport_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    venue_id: Optional[int] = None
    lock_venue: Optional[bool] = None
    max_participants: Optional[int] = None
    entry_fee: Optional[Decimal] = None
    cover_image: Optional[str] = None
    status: Optional[str] = None
    prize: Optional[str] = None

class TournamentBrief(BaseModel):
    id: int
    club_id: int
    title: str
    sport_type: Optional[str]
    start_time: datetime
    end_time: datetime
    venue_id: Optional[int]
    entry_fee: Decimal
    max_participants: Optional[int]
    current_participants: int
    cover_image: Optional[str]
    status: str
    created_at: datetime
    club_name: Optional[str] = None

    class Config:
        from_attributes = True

class TournamentDetail(TournamentBrief):
    description: Optional[str]
    prize: Optional[str] = None
    lock_venue: bool
    registrations: list["TournamentRegBrief"] = []

    class Config:
        from_attributes = True

class TournamentRegBrief(BaseModel):
    id: int
    user_id: PublicUserID
    status: str
    user_nickname: Optional[str] = None
    user_avatar: Optional[str] = None

    class Config:
        from_attributes = True

class TournamentListParams(BaseModel):
    club_id: Optional[int] = None
    sport: Optional[str] = None
    status: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# ── Settlement ──

class SettlementDetail(BaseModel):
    id: int
    order_id: int
    order_no: str
    total_amount: Decimal
    platform_amount: Decimal
    club_amount: Decimal
    split_ratio: Decimal
    status: str
    wx_split_order_no: Optional[str] = None
    out_order_no: Optional[str] = None
    retry_count: int
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    fail_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SettlementListParams(BaseModel):
    status: Optional[str] = None
    club_id: Optional[int] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class NotificationBrief(BaseModel):
    id: int
    type: str
    title: Optional[str]
    content: Optional[str]
    ref_id: Optional[int]
    ref_type: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stats ──

class ClubStats(BaseModel):
    total_venues: int
    total_orders: int
    total_revenue: Decimal
    venue_utilization: float  # percentage
    today_orders: int
    today_revenue: Decimal
    view_count: int
    exposure_count: int


# ── Upload ──

class UploadResponse(BaseModel):
    url: str
    filename: str
