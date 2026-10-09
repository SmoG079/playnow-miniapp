import enum
import uuid
from datetime import datetime, time
from sqlalchemy import (
    Column, BigInteger, String, Text, Integer, DateTime, Date, Time,
    Enum, Boolean, DECIMAL, UniqueConstraint, Index, ForeignKey, JSON,
    CheckConstraint, ForeignKeyConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import mysql
from app.core.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    club_admin = "club_admin"
    platform_admin = "platform_admin"


class User(Base):
    __tablename__ = "users"

    id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), primary_key=True, default=lambda context: context.get_current_parameters()["openid"])
    openid = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), nullable=False, unique=True)
    public_id = Column(String(36), nullable=False, unique=True, default=lambda context: str(uuid.uuid5(uuid.NAMESPACE_URL, "playnow:user:" + str(context.get_current_parameters().get("id") or context.get_current_parameters()["openid"]))))
    unionid = Column(String(64))
    nickname = Column(String(64))
    avatar_url = Column(String(512))
    phone = Column(String(20))
    session_key = Column(String(64))
    ntrp_level = Column(DECIMAL(2,1), nullable=True, comment='NTRP网球等级')
    utr_rating = Column(DECIMAL(4,2), nullable=True, comment='预留UTR等级，当前不赋值或展示')
    rating_assessment = Column(JSON, nullable=True, comment='定级问卷答案及算法版本')
    rating_assessed_at = Column(DateTime, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bookings = relationship("BookingOrder", back_populates="user")
    match_posts = relationship("MatchPost", back_populates="user")
    match_registrations = relationship("MatchRegistration", back_populates="user")
    tournament_registrations = relationship("TournamentRegistration", back_populates="user", foreign_keys="TournamentRegistration.user_id")
    managed_clubs = relationship("ClubMember", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    comments = relationship("Comment", back_populates="user")


class PrivateUpload(Base):
    __tablename__ = "private_uploads"
    id = Column(String(64), primary_key=True)  # Object filename, unguessable UUID.
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    backend = Column(String(16), nullable=False)
    content_type = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClubStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class Club(Base):
    __tablename__ = "clubs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    city = Column(String(64), nullable=True, index=True)
    name = Column(String(128), nullable=False)
    sport_types = Column(JSON, comment='["badminton","basketball"]')
    description = Column(Text)
    rules = Column(Text, comment='场地规则')
    cover_image = Column(String(512))
    images = Column(JSON)
    documents = Column(JSON, comment='PDF文件列表 [{name, url, size}]')
    address = Column(String(256))
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))
    contact_phone = Column(String(20))
    opening_time = Column(Time, default=time(8, 0), nullable=False)
    closing_time = Column(Time, default=time(22, 0), nullable=False)
    split_ratio = Column(DECIMAL(4, 3), default=0.100, nullable=False)
    sub_merchant_id = Column(String(64))
    view_count = Column(BigInteger, default=0, nullable=False)
    exposure_count = Column(BigInteger, default=0, nullable=False)
    status = Column(Enum(ClubStatus), default=ClubStatus.active, nullable=False)
    approval_status = Column(String(16), default="approved", server_default="approved", nullable=False)
    created_by = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=True)
    review_reason = Column(String(256), nullable=True)
    reviewed_by = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    __table_args__ = (Index("idx_club_approval_created", "approval_status", "created_at", "id"),
                     Index("idx_club_creator_created", "created_by", "created_at", "id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    venues = relationship("Venue", back_populates="club")
    members = relationship("ClubMember", back_populates="club")
    tournaments = relationship("Tournament", back_populates="club")
    bookings = relationship("BookingOrder", back_populates="club")
    match_posts = relationship("MatchPost", back_populates="club")


class ClubMemberRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"


class ClubMember(Base):
    __tablename__ = "club_members"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=False)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    role = Column(Enum(ClubMemberRole), default=ClubMemberRole.admin, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("club_id", "user_id", name="uq_club_user"),)

    club = relationship("Club", back_populates="members")
    user = relationship("User", back_populates="managed_clubs")


class VenueStatus(str, enum.Enum):
    active = "active"
    maintenance = "maintenance"
    closed = "closed"


class Venue(Base):
    __tablename__ = "venues"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    city = Column(String(64), nullable=True, index=True)
    address = Column(String(256), nullable=True)
    latitude = Column(DECIMAL(10, 7), nullable=True)
    longitude = Column(DECIMAL(10, 7), nullable=True)
    sport_type = Column(String(32), nullable=False)
    price_per_hour = Column(DECIMAL(10, 2), nullable=False)
    max_capacity = Column(Integer, default=4, nullable=False)
    cover_image = Column(String(512))
    price_rules = Column(JSON)  # [{type, start_date?, end_date?, start_time?, end_time?, price}]
    status = Column(Enum(VenueStatus), default=VenueStatus.active, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    club = relationship("Club", back_populates="venues")
    time_slots = relationship("VenueTimeSlot", back_populates="venue")
    bookings = relationship("BookingOrder", back_populates="venue")
    tournaments = relationship("Tournament", back_populates="venue")


class SlotStatus(str, enum.Enum):
    available = "available"
    locked = "locked"
    booked = "booked"
    maintenance = "maintenance"


class VenueTimeSlot(Base):
    __tablename__ = "venue_time_slots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    venue_id = Column(BigInteger, ForeignKey("venues.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    price_override = Column(DECIMAL(10, 2))
    status = Column(Enum(SlotStatus), default=SlotStatus.available, nullable=False)
    locked_by = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"))
    booking_order_id = Column(BigInteger, ForeignKey("booking_orders.id", name="fk_slot_booking_order", use_alter=True), nullable=True, index=True)
    locked_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("venue_id", "date", "start_time", name="uq_slot"),
        Index("idx_venue_date", "venue_id", "date"),
    )

    venue = relationship("Venue", back_populates="time_slots")
    bookings = relationship("BookingOrder", back_populates="slot", foreign_keys="BookingOrder.slot_id")


class OrderStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    cancelled = "cancelled"
    refunding = "refunding"
    refunded = "refunded"
    completed = "completed"


class RefundStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    success = "success"
    closed = "closed"
    abnormal = "abnormal"
    failed = "failed"


class BookingOrder(Base):
    __tablename__ = "booking_orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tournament_id = Column(BigInteger, ForeignKey("tournaments.id"), nullable=True, index=True)
    business_type = Column(String(16), default="booking", server_default="booking", nullable=False)
    order_no = Column(String(32), nullable=False, unique=True, index=True)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False, index=True)
    venue_id = Column(BigInteger, ForeignKey("venues.id"), nullable=True)
    slot_id = Column(BigInteger, ForeignKey("venue_time_slots.id"), nullable=True)
    slot_ids = Column(JSON, comment='选中的所有连续时段 ID 列表 [id1, id2, ...]')
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=True, index=True)
    amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending, index=True, nullable=False)
    payment_time = Column(DateTime)
    wx_transaction_id = Column(String(64))
    prepay_id = Column(String(64))
    prepay_id_created_at = Column(DateTime)
    cancel_reason = Column(String(256))
    cancel_time = Column(DateTime)
    refund_amount = Column(DECIMAL(10, 2))
    refund_id = Column(String(64))
    refund_time = Column(DateTime)
    refund_status = Column(Enum(RefundStatus, native_enum=False, length=32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    venue = relationship("Venue", back_populates="bookings")
    slot = relationship("VenueTimeSlot", back_populates="bookings", foreign_keys=[slot_id])
    club = relationship("Club", back_populates="bookings")
    settlement = relationship("SettlementRecord", back_populates="order", uselist=False)
    refund_records = relationship("RefundRecord", back_populates="order")
    __table_args__ = (Index("idx_pending_order_recovery", "business_type", "status", "updated_at", "id"),)


class BookingSlot(Base):
    __tablename__ = "booking_slots"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"), nullable=False)
    slot_id = Column(BigInteger, ForeignKey("venue_time_slots.id"), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=True)  # Historical per-slot quotes cannot be reconstructed.
    __table_args__ = (UniqueConstraint("order_id", "slot_id", name="uq_booking_slot"),)


class SettlementStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"), nullable=False, unique=True)
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    platform_amount = Column(DECIMAL(10, 2), nullable=False)
    club_amount = Column(DECIMAL(10, 2), nullable=False)
    split_ratio = Column(DECIMAL(4, 3), nullable=False)
    wx_split_order_no = Column(String(64))          # WeChat profit-sharing order id
    out_order_no = Column(String(64), unique=True)  # merchant profit-sharing order no
    status = Column(Enum(SettlementStatus), default=SettlementStatus.pending, nullable=False)
    fail_reason = Column(String(512))
    retry_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=False) # when settlement may execute
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    order = relationship("BookingOrder", back_populates="settlement")

    __table_args__ = (
        Index("idx_settlement_status_scheduled", "status", "scheduled_at"),
    )


class Activity(Base):
    __tablename__ = "activities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kind = Column(String(16).with_variant(mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"), "mysql"), nullable=False)
    legacy_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("id", "kind", name="uq_activity_id_kind"),
        UniqueConstraint("kind", "legacy_id", name="uq_activity_legacy"),
        CheckConstraint("kind IN ('post', 'tournament')", name="ck_activity_kind"),
        {"sqlite_autoincrement": True},
    )


class MatchPostStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    full = "full"


class MatchPost(Base):
    __tablename__ = "match_posts"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    activity_kind = Column(String(16).with_variant(mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"), "mysql"), default="post", server_default="post", nullable=False)
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=True)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    city = Column(String(64), nullable=True, index=True)
    address = Column(String(256), nullable=True)
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))
    title = Column(String(256), nullable=False)
    sport_type = Column(String(32))
    preferred_date = Column(Date, index=True)
    preferred_start = Column(Time)
    preferred_end = Column(Time)
    players_needed = Column(Integer, default=1)
    price = Column(DECIMAL(10, 2), nullable=True, comment='人均费用')
    level_required = Column(String(32))
    notes = Column(Text)
    description = Column(Text)
    documents = Column(JSON)
    images = Column(JSON)
    venue_id = Column(BigInteger, ForeignKey("venues.id"))
    booking_id = Column(BigInteger, ForeignKey("booking_orders.id"))
    group_chat_id = Column(String(64))
    approval_required = Column(Boolean, default=False, nullable=False)
    status = Column(Enum(MatchPostStatus), default=MatchPostStatus.open, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index("idx_club_status", "club_id", "status"),
        ForeignKeyConstraint(["id", "activity_kind"], ["activities.id", "activities.kind"],
                             name="fk_post_activity"),
        CheckConstraint("activity_kind = 'post'", name="ck_post_activity_kind"),
    )

    club = relationship("Club", back_populates="match_posts")
    user = relationship("User", back_populates="match_posts")
    registrations = relationship("MatchRegistration", back_populates="post")
    comments = relationship("Comment", back_populates="post", order_by="Comment.created_at.desc()")


class RegistrationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class MatchRegistration(Base):
    __tablename__ = "match_registrations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("match_posts.id"), nullable=False)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    message = Column(String(256))
    review_reason = Column(String(256), nullable=True)
    status = Column(Enum(RegistrationStatus), default=RegistrationStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user"),
                     Index("idx_post_registration_user_created", "user_id", "created_at", "id"),
                     Index("idx_post_review", "post_id", "status"))

    post = relationship("MatchPost", back_populates="registrations")
    user = relationship("User", back_populates="match_registrations")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("match_posts.id"), nullable=False, index=True)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    parent_id = Column(BigInteger, ForeignKey("comments.id"), nullable=True)
    content = Column(String(512), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    post = relationship("MatchPost", back_populates="comments")
    user = relationship("User", back_populates="comments")
    replies = relationship("Comment", back_populates="parent")
    parent = relationship("Comment", back_populates="replies", remote_side=[id])


class TournamentStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    ongoing = "ongoing"
    finished = "finished"
    cancelled = "cancelled"


class Tournament(Base):
    __tablename__ = "tournaments"

    id = Column(BigInteger, primary_key=True, autoincrement=False)
    activity_kind = Column(String(16).with_variant(mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"), "mysql"), default="tournament", server_default="tournament", nullable=False)
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=True, index=True)
    city = Column(String(64), nullable=True, index=True)
    latitude = Column(DECIMAL(10, 7))
    longitude = Column(DECIMAL(10, 7))
    title = Column(String(256), nullable=False)
    description = Column(Text)
    sport_type = Column(String(32))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    venue_id = Column(BigInteger, ForeignKey("venues.id"))
    lock_venue = Column(Boolean, default=False, nullable=False)
    max_participants = Column(Integer)
    current_participants = Column(Integer, default=0, nullable=False)
    entry_fee = Column(DECIMAL(10, 2), default=0, nullable=False)
    prize = Column(String(256))
    images = Column(JSON)
    cover_image = Column(String(512))
    config = Column(JSON, nullable=True)
    address = Column(String(256))
    contact_name = Column(String(64))
    contact_phone = Column(String(20))
    auto_title = Column(Boolean, default=False, nullable=False)
    registration_deadline = Column(DateTime)
    cancellation_deadline = Column(DateTime)
    registration_closed = Column(Boolean, default=False, nullable=False)
    roster_frozen = Column(Boolean, default=False, nullable=False)
    draw_version = Column(Integer, default=0, nullable=False)
    published_version = Column(Integer, default=0, nullable=False)
    group_chat_id = Column(String(64))
    status = Column(Enum(TournamentStatus), default=TournamentStatus.open, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        Index("idx_status_time", "status", "start_time"),
        ForeignKeyConstraint(["id", "activity_kind"], ["activities.id", "activities.kind"],
                             name="fk_tournament_activity"),
        CheckConstraint("activity_kind = 'tournament'", name="ck_tournament_activity_kind"),
    )

    club = relationship("Club", back_populates="tournaments")
    venue = relationship("Venue", back_populates="tournaments")
    registrations = relationship("TournamentRegistration", back_populates="tournament")


class TournamentRegStatus(str, enum.Enum):
    registered = "registered"
    confirmed = "confirmed"
    cancelled = "cancelled"


class TournamentRegistration(Base):
    __tablename__ = "tournament_registrations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tournament_id = Column(BigInteger, ForeignKey("tournaments.id"), nullable=False)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"))
    status = Column(Enum(TournamentRegStatus), default=TournamentRegStatus.registered, nullable=False)
    approval = Column(String(16), default="approved", nullable=False)
    payment = Column(String(16), default="none", nullable=False)
    admission = Column(String(16), default="active", nullable=False)
    gender = Column(String(16))
    requested_group = Column(Integer, default=0, server_default="0", nullable=False)
    pairing = Column(String(16), default="random", nullable=False)
    partner_user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"))
    invite_token = Column(String(64), unique=True)
    seat_expires_at = Column(DateTime)
    review_reason = Column(String(256))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_tournament_user"),
                     Index("idx_tournament_registration_user_created", "user_id", "created_at", "id"),
                     Index("idx_tournament_review", "tournament_id", "approval", "admission"))

    tournament = relationship("Tournament", back_populates="registrations")
    user = relationship("User", back_populates="tournament_registrations", foreign_keys=[user_id])


class NotificationType(str, enum.Enum):
    booking = "booking"
    match = "match"
    tournament = "tournament"
    system = "system"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(Enum(NotificationType), nullable=False)
    title = Column(String(128))
    content = Column(String(512))
    ref_id = Column(BigInteger)
    ref_type = Column(String(32))
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("idx_user_read", "user_id", "is_read"),)

    user = relationship("User", back_populates="notifications")


class RefundRecord(Base):
    __tablename__ = "refund_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"), nullable=False)
    out_refund_no = Column(String(32), nullable=False, unique=True)
    wx_refund_id = Column(String(64))
    amount = Column(DECIMAL(10, 2), nullable=False)
    reason = Column(String(256))
    status = Column(Enum(RefundStatus, native_enum=False, length=32), default=RefundStatus.pending, nullable=False)
    retry_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    fail_reason = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    __table_args__ = (
        Index("idx_refund_order", "order_id"),
        Index("idx_refund_status_scheduled", "status", "scheduled_at"),
    )

    order = relationship("BookingOrder", back_populates="refund_records")


class PaymentLog(Base):
    __tablename__ = "payment_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger)
    type = Column(String(32))
    event_type = Column(String(64))
    raw_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_payment_order", "order_id"),)


class TournamentDraw(Base):
    __tablename__ = "tournament_draws"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tournament_id = Column(BigInteger, ForeignKey("tournaments.id"), nullable=False)
    version = Column(Integer, nullable=False)
    stage = Column(String(16), nullable=False)
    idempotency_key = Column(String(64), nullable=False)
    seed = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_by = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    reason = Column(String(256))
    published_at = Column(DateTime)
    tie_orders = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("tournament_id", "version", name="uq_tournament_draw_version"),
                     UniqueConstraint("tournament_id", "idempotency_key", name="uq_tournament_draw_key"))


class TournamentTeam(Base):
    __tablename__ = "tournament_teams"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    draw_id = Column(BigInteger, ForeignKey("tournament_draws.id"), nullable=False, index=True)
    group_no = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    origin_group = Column(Integer)
    __table_args__ = (UniqueConstraint("id", "draw_id", name="uq_team_draw"),)


class TournamentTeamMember(Base):
    __tablename__ = "tournament_team_members"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    draw_id = Column(BigInteger, ForeignKey("tournament_draws.id"), nullable=False)
    team_id = Column(BigInteger, ForeignKey("tournament_teams.id"), nullable=False)
    user_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
    __table_args__ = (UniqueConstraint("draw_id", "user_id", name="uq_draw_member"),
        ForeignKeyConstraint(["team_id", "draw_id"], ["tournament_teams.id", "tournament_teams.draw_id"], name="fk_member_team_draw"))


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    draw_id = Column(BigInteger, ForeignKey("tournament_draws.id"), nullable=False, index=True)
    group_no = Column(Integer, nullable=False)
    round_no = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)
    kind = Column(String(16), nullable=False)
    team_a_id = Column(BigInteger, ForeignKey("tournament_teams.id"))
    team_b_id = Column(BigInteger, ForeignKey("tournament_teams.id"))
    source_a_id = Column(BigInteger, ForeignKey("tournament_matches.id"))
    source_b_id = Column(BigInteger, ForeignKey("tournament_matches.id"))
    source_outcome = Column(String(16), default="winner", nullable=False)
    winner_id = Column(BigInteger, ForeignKey("tournament_teams.id"))
    score = Column(String(128))
    is_draw = Column(Boolean, default=False, nullable=False)
    walkover = Column(Boolean, default=False, nullable=False)
    status = Column(String(16), default="pending", nullable=False)
    court = Column(String(64))
    scheduled_at = Column(DateTime)
    scheduled_end = Column(DateTime)
    __table_args__ = (UniqueConstraint("draw_id", "group_no", "round_no", "position", "kind", name="uq_draw_match"),
        UniqueConstraint("id", "draw_id", name="uq_match_draw"),
        ForeignKeyConstraint(["team_a_id", "draw_id"], ["tournament_teams.id", "tournament_teams.draw_id"], name="fk_match_team_a_draw"),
        ForeignKeyConstraint(["team_b_id", "draw_id"], ["tournament_teams.id", "tournament_teams.draw_id"], name="fk_match_team_b_draw"),
        ForeignKeyConstraint(["winner_id", "draw_id"], ["tournament_teams.id", "tournament_teams.draw_id"], name="fk_match_winner_draw"),
        ForeignKeyConstraint(["source_a_id", "draw_id"], ["tournament_matches.id", "tournament_matches.draw_id"], name="fk_match_source_a_draw"),
        ForeignKeyConstraint(["source_b_id", "draw_id"], ["tournament_matches.id", "tournament_matches.draw_id"], name="fk_match_source_b_draw"))


class TournamentAudit(Base):
    __tablename__ = "tournament_audits"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tournament_id = Column(BigInteger, ForeignKey("tournaments.id"), nullable=False, index=True)
    actor_id = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"))
    action = Column(String(32), nullable=False)
    detail = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserIDMigration(Base):
    __tablename__ = "user_id_migrations"
    legacy_id = Column(BigInteger, primary_key=True, autoincrement=False)
    openid = Column(String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql"), ForeignKey("users.id"), nullable=False)
