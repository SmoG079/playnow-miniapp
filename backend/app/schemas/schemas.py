from datetime import datetime, date, time as dt_time
from typing import Optional, Any, List
from pydantic import BaseModel, Field, field_serializer, field_validator
from decimal import Decimal


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
    id: int
    nickname: Optional[str]
    avatar_url: Optional[str]
    phone: Optional[str]
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    ntrp_level: Optional[Decimal] = Field(None, ge=1.0, le=7.0)

class UserMeResponse(UserProfile):
    managed_club_ids: list[int] = []
    ntrp_level: Optional[Decimal] = None


# ── Club ──

class ClubCreate(BaseModel):
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

class ClubUpdate(BaseModel):
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

class ClubBrief(BaseModel):
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
    distance: Optional[float] = None  # km, rounded to 1 decimal

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

class ClubListParams(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    sport: Optional[str] = None
    keyword: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


# ── Venue ──

class VenueCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    sport_type: str = "tennis"
    price_per_hour: Decimal = Field(..., gt=0)
    max_capacity: int = Field(default=4, ge=1)
    open_time: str = "08:00"
    close_time: str = "22:00"
    cover_image: Optional[str] = None
    sort_order: int = 0
    opening_time: Optional[time] = time(8, 0)
    closing_time: Optional[time] = time(22, 0)
    slot_interval_minutes: Optional[int] = Field(default=60, ge=30)

class VenueUpdate(BaseModel):
    name: Optional[str] = None
    sport_type: Optional[str] = None
    price_per_hour: Optional[Decimal] = None
    max_capacity: Optional[int] = None
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    cover_image: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    slot_interval_minutes: Optional[int] = Field(default=None, ge=30)

def _coerce_time(v):
    """Convert datetime.time -> 'HH:MM' string for ORM validation."""
    if v is None:
        return None
    if isinstance(v, dt_time):
        return v.strftime("%H:%M")
    return v


class VenueBrief(BaseModel):
    id: int
    club_id: int
    name: str
    sport_type: str
    price_per_hour: Decimal
    max_capacity: int
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    cover_image: Optional[str]
    status: str
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    slot_interval_minutes: int = 60

    _v_open = field_validator("open_time", mode="before")(_coerce_time)
    _v_close = field_validator("close_time", mode="before")(_coerce_time)

    @field_serializer("open_time", "close_time")
    def _serialize_time(self, v):
        return _coerce_time(v)

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
    price: Decimal = Field(gt=0)


class SlotGenerateRequest(BaseModel):
    date_from: date
    date_to: date
    start_time: dt_time = dt_time(8, 0)
    end_time: dt_time = dt_time(22, 0)
    interval_minutes: int = Field(default=60, ge=30)
    price_rules: list[SlotPriceRule] = Field(default_factory=list)

class SlotBrief(BaseModel):
    id: int
    venue_id: int
    date: date
    start_time: dt_time
    end_time: dt_time
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
    slot_id: int
    slot2_id: Optional[int] = None  # second 30-min slot for 1-hour booking

class BookingDetail(BaseModel):
    id: int
    order_no: str
    user_id: int
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
    slot_start: Optional[dt_time] = None
    slot_end: Optional[dt_time] = None

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
    club_id: int
    title: str = Field(..., min_length=1, max_length=256)
    sport_type: Optional[str] = None
    preferred_date: date
    preferred_start: time
    preferred_end: time
    players_needed: int = Field(default=1, ge=1)
    price: Decimal = Field(..., ge=Decimal("0.00"))
    level_required: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    documents: Optional[list[dict]] = None
    venue_id: Optional[int] = None
    booking_id: Optional[int] = None
    approval_required: bool = False

class PostUpdate(BaseModel):
    title: Optional[str] = None
    sport_type: Optional[str] = None
    preferred_date: Optional[date] = None
    preferred_start: Optional[dt_time] = None
    preferred_end: Optional[dt_time] = None
    players_needed: int = Field(default=1, ge=1)
    level_required: Optional[str] = None
    notes: Optional[str] = None
    description: Optional[str] = None
    documents: Optional[list[dict]] = None
    venue_id: Optional[int] = None
    booking_id: Optional[int] = None
    approval_required: Optional[bool] = None

class PostBrief(BaseModel):
    id: int
    club_id: int
    user_id: int
    title: str
    sport_type: Optional[str]
    preferred_date: Optional[date]
    preferred_start: Optional[dt_time]
    preferred_end: Optional[dt_time]
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
    venue_id: Optional[int] = None
    booking_id: Optional[int] = None

    class Config:
        from_attributes = True

class PostDetail(PostBrief):
    notes: Optional[str]
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
    user_id: int
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
    status: str  # approved / rejected


# ── Comment ──

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=512)
    parent_id: Optional[int] = None

class CommentBrief(BaseModel):
    id: int
    post_id: int
    user_id: int
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
    club_id: int
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    sport_type: Optional[str] = None
    start_time: datetime
    end_time: datetime
    venue_id: Optional[int] = None
    lock_venue: bool = False
    max_participants: Optional[int] = None
    entry_fee: Decimal = Decimal("0")
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
    user_id: int
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
