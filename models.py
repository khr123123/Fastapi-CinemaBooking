"""
データモデル定義 - Pydantic & SQLAlchemy
高並行チケット予約システム
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ========== SQLAlchemy ORM モデル ==========

class Movie(Base):
    """映画情報"""
    __tablename__ = "movies"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    duration = Column(Integer, default=120)  # 分
    rating = Column(Float, default=8.0)
    poster_url = Column(String(500))
    description = Column(String(1000))
    showtimes = relationship("Showtime", back_populates="movie")


class Showtime(Base):
    """上映回情報"""
    __tablename__ = "showtimes"
    id = Column(Integer, primary_key=True, index=True)
    movie_id = Column(Integer, ForeignKey("movies.id"))
    hall_name = Column(String(50))
    start_time = Column(DateTime, nullable=False)
    price = Column(Float, default=1500.0)
    total_seats = Column(Integer, default=64)  # 8x8席
    movie = relationship("Movie", back_populates="showtimes")
    seats = relationship("Seat", back_populates="showtime")


class Seat(Base):
    """座席（楽観的ロック用 version カラム付き）"""
    __tablename__ = "seats"
    id = Column(Integer, primary_key=True, index=True)
    showtime_id = Column(Integer, ForeignKey("showtimes.id"), index=True)
    row_num = Column(Integer)
    col_num = Column(Integer)
    is_booked = Column(Boolean, default=False)
    locked_until = Column(DateTime, nullable=True)  # 一時ロック期限
    locked_by = Column(String(100), nullable=True)  # ユーザーID
    version = Column(Integer, default=0)  # 楽観的ロック用
    showtime = relationship("Showtime", back_populates="seats")


class Order(Base):
    """注文"""
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String(50), unique=True, index=True)
    user_id = Column(String(100), index=True)
    showtime_id = Column(Integer, ForeignKey("showtimes.id"))
    seat_ids = Column(String(500))  # "1,2,3" 形式
    total_price = Column(Float)
    status = Column(String(20), default="PENDING")  # PENDING/PAID/CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== Pydantic スキーマ ==========

class SeatStatus(str, Enum):
    AVAILABLE = "available"
    LOCKED = "locked"
    BOOKED = "booked"


class SeatSchema(BaseModel):
    id: int
    row_num: int
    col_num: int
    status: SeatStatus

    class Config:
        from_attributes = True


class MovieSchema(BaseModel):
    id: int
    title: str
    duration: int
    rating: float
    poster_url: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True


class ShowtimeSchema(BaseModel):
    id: int
    movie_id: int
    movie_title: str
    hall_name: str
    start_time: datetime
    price: float
    available_seats: int

    class Config:
        from_attributes = True


class LockSeatRequest(BaseModel):
    showtime_id: int
    seat_ids: List[int]
    user_id: str = Field(..., min_length=1)


class LockSeatResponse(BaseModel):
    success: bool
    locked_seats: List[int]
    failed_seats: List[int]
    expires_at: Optional[datetime] = None
    message: str


class CreateOrderRequest(BaseModel):
    showtime_id: int
    seat_ids: List[int]
    user_id: str


class OrderSchema(BaseModel):
    id: int
    order_no: str
    user_id: str
    showtime_id: int
    seat_ids: str
    total_price: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
