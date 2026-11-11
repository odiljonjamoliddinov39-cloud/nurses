"""Data model — see ARCHITECTURE.md section 5."""
import enum
from datetime import datetime

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Enum, Float,
                        ForeignKey, Integer, String, Table, Column, Text, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class UserStatus(str, enum.Enum):
    guest = "guest"
    pending = "pending"
    subscriber = "subscriber"
    expired = "expired"
    blocked = "blocked"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SubscriptionSource(str, enum.Enum):
    payment = "payment"
    gift = "gift"
    promo = "promo"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    cancelled = "cancelled"


class AttemptState(str, enum.Enum):
    recorded = "recorded"
    transcribed = "transcribed"
    grading = "grading"
    graded = "graded"
    failed_retry = "failed_retry"  # STT/LLM down; retried automatically


plan_courses = Table(
    "plan_courses", Base.metadata,
    Column("plan_id", ForeignKey("plans.id"), primary_key=True),
    Column("course_id", ForeignKey("courses.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    full_name: Mapped[str | None] = mapped_column(String(200))
    ui_language: Mapped[str] = mapped_column(String(2), default="uz")  # uz/ru/en
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.guest)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[dict] = mapped_column(JSON)  # {"uz":..,"ru":..,"en":..}
    description: Mapped[dict | None] = mapped_column(JSON)
    cover: Mapped[str | None] = mapped_column(String(500))
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    topics: Mapped[list["Topic"]] = relationship(back_populates="course")


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    order: Mapped[int] = mapped_column(Integer, default=0)
    course: Mapped[Course] = relationship(back_populates="topics")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    model_answer: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    question_audio: Mapped[str | None] = mapped_column(String(500))
    answer_audio: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    key_points: Mapped[list["KeyPoint"]] = relationship(back_populates="question")
    mcq_options: Mapped[list["McqOption"]] = relationship(back_populates="question")


class KeyPoint(Base):
    __tablename__ = "key_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    question: Mapped[Question] = relationship(back_populates="key_points")


class McqOption(Base):
    __tablename__ = "mcq_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    question: Mapped[Question] = relationship(back_populates="mcq_options")


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    days: Mapped[int] = mapped_column(Integer)
    price_uzs: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    courses: Mapped[list[Course]] = relationship(secondary=plan_courses)


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    amount: Mapped[int] = mapped_column(Integer)
    payment_code: Mapped[str] = mapped_column(String(16), unique=True)  # e.g. "#4821"
    receipt_image: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.pending)
    reject_reason: Mapped[str | None] = mapped_column(String(300))
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)  # admin telegram_id
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[SubscriptionSource] = mapped_column(Enum(SubscriptionSource))
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), default=SubscriptionStatus.active)


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="oral")  # oral/mock/test
    state: Mapped[AttemptState] = mapped_column(Enum(AttemptState), default=AttemptState.recorded)
    audio_file: Mapped[str | None] = mapped_column(String(500))
    transcript: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    covered_points: Mapped[list | None] = mapped_column(JSON)
    missed_points: Mapped[list | None] = mapped_column(JSON)
    wrong_statements: Mapped[list | None] = mapped_column(JSON)
    comment: Mapped[str | None] = mapped_column(Text)
    what_to_add: Mapped[str | None] = mapped_column(Text)
    ai_cost: Mapped[float] = mapped_column(Float, default=0.0)
    manual_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Favourite(Base):
    __tablename__ = "favourites"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)


class Broadcast(Base):
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(500))
    button: Mapped[dict | None] = mapped_column(JSON)
    segment: Mapped[str] = mapped_column(String(64), default="all")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_count: Mapped[int] = mapped_column(Integer, default=0)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSON)


class UiText(Base):
    """Editable UI strings, per language."""
    __tablename__ = "ui_texts"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    lang: Mapped[str] = mapped_column(String(2), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(100))
    object: Mapped[str] = mapped_column(String(200))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
