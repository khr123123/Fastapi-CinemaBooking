"""
FastAPI メインアプリケーション
高並行チケット予約 API
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_
from sqlalchemy.orm import Session

from database import get_db, init_db, SessionLocal
from models import (
    Movie, Showtime, Seat, Order,
    MovieSchema, ShowtimeSchema, SeatSchema, SeatStatus,
    LockSeatRequest, LockSeatResponse,
    CreateOrderRequest, OrderSchema,
)
from seat_lock import seat_lock_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動時にDB初期化"""
    import os
    if not os.path.exists("cinema.db"):
        init_db()
    yield


app = FastAPI(
    title="🎬 Cinema Booking API",
    description="高並行映画チケット予約システム",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 同期 DB ヘルパー（threadpool で実行される） ==========

def _check_booked_in_db(showtime_id: int, seat_ids: List[int]) -> List[int]:
    db = SessionLocal()
    try:
        booked = db.query(Seat).filter(
            and_(
                Seat.showtime_id == showtime_id,
                Seat.id.in_(seat_ids),
                Seat.is_booked == True,
            )
        ).all()
        return [s.id for s in booked]
    finally:
        db.close()


def _book_seats_in_db(
        showtime_id: int, seat_ids: List[int], user_id: str
) -> dict:
    """
    DB で楽観的ロック予約を実行
    Returns: {"success": bool, "order": Order or None, "error": str}
    """
    db = SessionLocal()
    try:
        showtime = db.query(Showtime).filter(Showtime.id == showtime_id).first()
        if not showtime:
            return {"success": False, "error": "上映回が見つかりません"}

        seats = db.query(Seat).filter(
            and_(
                Seat.showtime_id == showtime_id,
                Seat.id.in_(seat_ids),
            )
        ).all()
        if len(seats) != len(seat_ids):
            return {"success": False, "error": "座席が見つかりません"}

        for seat in seats:
            if seat.is_booked:
                return {"success": False, "error": f"座席{seat.id}は既に予約済み"}
            old_version = seat.version
            updated = db.query(Seat).filter(
                and_(Seat.id == seat.id, Seat.version == old_version)
            ).update({
                "is_booked": True,
                "version": old_version + 1,
                "locked_by": user_id,
            })
            if updated == 0:
                db.rollback()
                return {"success": False, "error": f"座席{seat.id}の更新失敗（並行競合）"}

        order_no = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        total_price = showtime.price * len(seat_ids)
        order = Order(
            order_no=order_no,
            user_id=user_id,
            showtime_id=showtime_id,
            seat_ids=",".join(map(str, seat_ids)),
            total_price=total_price,
            status="PAID",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return {
            "success": True,
            "order": {
                "id": order.id,
                "order_no": order.order_no,
                "user_id": order.user_id,
                "showtime_id": order.showtime_id,
                "seat_ids": order.seat_ids,
                "total_price": order.total_price,
                "status": order.status,
                "created_at": order.created_at,
            },
        }
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# ========== 映画・上映回 API ==========

@app.get("/api/movies", response_model=List[MovieSchema])
def list_movies(db: Session = Depends(get_db)):
    return db.query(Movie).all()


@app.get("/api/showtimes/{movie_id}", response_model=List[ShowtimeSchema])
async def list_showtimes(movie_id: int):
    def _query():
        db = SessionLocal()
        try:
            movie = db.query(Movie).filter(Movie.id == movie_id).first()
            if not movie:
                return None
            showtimes = db.query(Showtime).filter(Showtime.movie_id == movie_id).all()
            data = []
            for st in showtimes:
                booked_count = db.query(Seat).filter(
                    and_(Seat.showtime_id == st.id, Seat.is_booked == True)
                ).count()
                data.append({
                    "id": st.id,
                    "movie_id": st.movie_id,
                    "movie_title": movie.title,
                    "hall_name": st.hall_name,
                    "start_time": st.start_time,
                    "price": st.price,
                    "booked_count": booked_count,
                    "total_seats": st.total_seats,
                })
            return data
        finally:
            db.close()

    data = await run_in_threadpool(_query)
    if data is None:
        raise HTTPException(404, "映画が見つかりません")

    result = []
    for st in data:
        locked = await seat_lock_manager.get_locked_seats(st["id"])
        available = st["total_seats"] - st["booked_count"] - len(locked)
        result.append(ShowtimeSchema(
            id=st["id"],
            movie_id=st["movie_id"],
            movie_title=st["movie_title"],
            hall_name=st["hall_name"],
            start_time=st["start_time"],
            price=st["price"],
            available_seats=available,
        ))
    return result


@app.get("/api/seats/{showtime_id}", response_model=List[SeatSchema])
async def list_seats(showtime_id: int):
    """座席状態取得（予約済み/ロック中/空席）"""

    def _query():
        db = SessionLocal()
        try:
            seats = db.query(Seat).filter(Seat.showtime_id == showtime_id).all()
            return [
                {"id": s.id, "row_num": s.row_num, "col_num": s.col_num,
                 "is_booked": s.is_booked}
                for s in seats
            ]
        finally:
            db.close()

    seats = await run_in_threadpool(_query)
    if not seats:
        raise HTTPException(404, "上映回が見つかりません")

    locked_map = await seat_lock_manager.get_locked_seats(showtime_id)
    result = []
    for s in seats:
        if s["is_booked"]:
            status_val = SeatStatus.BOOKED
        elif s["id"] in locked_map:
            status_val = SeatStatus.LOCKED
        else:
            status_val = SeatStatus.AVAILABLE
        result.append(SeatSchema(
            id=s["id"], row_num=s["row_num"], col_num=s["col_num"],
            status=status_val
        ))
    return result


# ========== 座席ロック API（高並行制御の核） ==========

@app.post("/api/seats/lock", response_model=LockSeatResponse)
async def lock_seats(req: LockSeatRequest):
    """
    座席を一時ロック（5分間）
    高並行で複数ユーザーが同時アクセスしても整合性を保証
    """
    # ステップ1: DB状態チェック（threadpool で実行）
    booked_ids = await run_in_threadpool(
        _check_booked_in_db, req.showtime_id, req.seat_ids
    )
    if booked_ids:
        return LockSeatResponse(
            success=False,
            locked_seats=[],
            failed_seats=booked_ids,
            message=f"座席 {booked_ids} は既に予約済みです",
        )

    # ステップ2: メモリ内ロック取得（asyncio.Lock で原子的）
    success, locked, conflicts = await seat_lock_manager.try_lock_seats(
        req.showtime_id, req.seat_ids, req.user_id
    )

    if success:
        return LockSeatResponse(
            success=True,
            locked_seats=locked,
            failed_seats=[],
            expires_at=datetime.now() + timedelta(seconds=300),
            message=f"{len(locked)}席のロック成功（5分間有効）",
        )
    else:
        return LockSeatResponse(
            success=False,
            locked_seats=[],
            failed_seats=conflicts,
            message=f"座席 {conflicts} は他のユーザーがロック中です",
        )


@app.post("/api/seats/release")
async def release_seats(req: LockSeatRequest):
    """ロック解放"""
    n = await seat_lock_manager.release_seats(
        req.showtime_id, req.seat_ids, req.user_id
    )
    return {"released": n, "message": f"{n}席のロックを解放しました"}


# ========== 注文API（楽観的ロックでDB更新） ==========

@app.post("/api/orders", response_model=OrderSchema)
async def create_order(req: CreateOrderRequest):
    """
    注文作成
    1. メモリロック確認
    2. DB楽観的ロック（version カラム）で原子的更新
    3. 注文レコード作成
    """
    # ステップ1: メモリロック確認
    confirmed = await seat_lock_manager.confirm_seats(
        req.showtime_id, req.seat_ids, req.user_id
    )
    if not confirmed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "座席ロックが無効です。再度座席を選択してください。"
        )

    # ステップ2: DB書き込み（threadpool で実行）
    result = await run_in_threadpool(
        _book_seats_in_db, req.showtime_id, req.seat_ids, req.user_id
    )

    if not result["success"]:
        raise HTTPException(409, result["error"])

    # ステップ3: ロック解放
    await seat_lock_manager.release_seats(
        req.showtime_id, req.seat_ids, req.user_id
    )

    return result["order"]


@app.get("/api/orders/{user_id}", response_model=List[OrderSchema])
def list_user_orders(user_id: str, db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.user_id == user_id).order_by(
        Order.created_at.desc()
    ).all()


# ========== 監視API ==========

@app.get("/api/stats")
async def get_stats():
    """システム統計（モニタリング用）"""

    def _query():
        db = SessionLocal()
        try:
            total_orders = db.query(Order).count()
            paid = db.query(Order).filter(Order.status == "PAID").all()
            revenue = sum(o.total_price for o in paid)
            return total_orders, revenue
        finally:
            db.close()

    total_orders, revenue = await run_in_threadpool(_query)
    return {
        "lock_stats": seat_lock_manager.get_stats(),
        "total_orders": total_orders,
        "total_revenue": revenue,
        "active_locks": len(seat_lock_manager._locks),
    }


@app.get("/")
def root():
    return {
        "service": "🎬 Cinema Booking API",
        "version": "1.0.0",
        "docs": "/docs",
    }
