import enum
from datetime import datetime, time
from sqlalchemy import (
    Column, BigInteger, String, Text, Integer, DateTime, Date, Time,
    Enum, Boolean, DECIMAL, UniqueConstraint, Index, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    club_admin = "club_admin"
    platform_admin = "platform_admin"


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    openid = Column(String(64), nullable=False, unique=True)
    unionid = Column(String(64))
    nickname = Column(String(64))
    avatar_url = Column(String(512))
    phone = Column(String(20))
    session_key = Column(String(64))
    ntrp_level = Column(DECIMAL(2,1), nullable=True, comment='NTRP网球等级')
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bookings = relationship("BookingOrder", back_populates="user")
    match_posts = relationship("MatchPost", back_populates="user")
    match_registrations = relationship("MatchRegistration", back_populates="user")
    tournament_registrations = relationship("TournamentRegistration", back_populates="user")
    managed_clubs = relationship("ClubMember", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    comments = relationship("Comment", back_populates="user")


class ClubStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class Club(Base):
    __tablename__ = "clubs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
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
    split_ratio = Column(DECIMAL(4, 3), default=0.100, nullable=False)
    sub_merchant_id = Column(String(64))
    view_count = Column(BigInteger, default=0, nullable=False)
    exposure_count = Column(BigInteger, default=0, nullable=False)
    status = Column(Enum(ClubStatus), default=ClubStatus.active, nullable=False)
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
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
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
    sport_type = Column(String(32), nullable=False, default="tennis")
    price_per_hour = Column(DECIMAL(10, 2), nullable=False)
    max_capacity = Column(Integer, default=4)
    open_time = Column(Time, default=time(8, 0))
    close_time = Column(Time, default=time(22, 0))
    cover_image = Column(String(512))
    status = Column(Enum(VenueStatus), default=VenueStatus.active, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    opening_time = Column(Time, default=time(8, 0), nullable=False)
    closing_time = Column(Time, default=time(22, 0), nullable=False)
    slot_interval_minutes = Column(Integer, default=60, nullable=False)
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
    locked_by = Column(BigInteger, ForeignKey("users.id"))
    locked_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("venue_id", "date", "start_time", name="uq_slot"),
        Index("idx_venue_date", "venue_id", "date"),
    )

    venue = relationship("Venue", back_populates="time_slots")
    bookings = relationship("BookingOrder", back_populates="slot")


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
    order_no = Column(String(32), nullable=False, unique=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    venue_id = Column(BigInteger, ForeignKey("venues.id"), nullable=False)
    slot_id = Column(BigInteger, ForeignKey("venue_time_slots.id"), nullable=True)
    slot_ids = Column(JSON, comment='选中的所有连续时段 ID 列表 [id1, id2, ...]')
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=False, index=True)
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
    slot = relationship("VenueTimeSlot", back_populates="bookings")
    club = relationship("Club", back_populates="bookings")
    settlement = relationship("SettlementRecord", back_populates="order", uselist=False)
    refund_records = relationship("RefundRecord", back_populates="order")


class SettlementStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SettlementRecord(Base):
    __tablename__ = "settlement_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"), nullable=False)
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


class MatchPostStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    full = "full"


class MatchPost(Base):
    __tablename__ = "match_posts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
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
    venue_id = Column(BigInteger, ForeignKey("venues.id"))
    booking_id = Column(BigInteger, ForeignKey("booking_orders.id"))
    group_chat_id = Column(String(64))
    approval_required = Column(Boolean, default=False, nullable=False)
    status = Column(Enum(MatchPostStatus), default=MatchPostStatus.open, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("idx_club_status", "club_id", "status"),)

    club = relationship("Club", back_populates="match_posts")
    user = relationship("User", back_populates="match_posts")
    registrations = relationship("MatchRegistration", back_populates="post")
    comments = relationship("Comment", back_populates="post", order_by="Comment.created_at.desc()")


class RegistrationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MatchRegistration(Base):
    __tablename__ = "match_registrations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("match_posts.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    message = Column(String(256))
    status = Column(Enum(RegistrationStatus), default=RegistrationStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user"),)

    post = relationship("MatchPost", back_populates="registrations")
    user = relationship("User", back_populates="match_registrations")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("match_posts.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
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

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    club_id = Column(BigInteger, ForeignKey("clubs.id"), nullable=False, index=True)
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
    cover_image = Column(String(512))
    group_chat_id = Column(String(64))
    status = Column(Enum(TournamentStatus), default=TournamentStatus.draft, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (Index("idx_status_time", "status", "start_time"),)

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
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    order_id = Column(BigInteger, ForeignKey("booking_orders.id"))
    status = Column(Enum(TournamentRegStatus), default=TournamentRegStatus.registered, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_tournament_user"),)

    tournament = relationship("Tournament", back_populates="registrations")
    user = relationship("User", back_populates="tournament_registrations")


class NotificationType(str, enum.Enum):
    booking = "booking"
    match = "match"
    tournament = "tournament"
    system = "system"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
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
