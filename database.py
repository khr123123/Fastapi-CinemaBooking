"""
データベース設定とシードデータ
"""
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Movie, Showtime, Seat

# SQLite を使用（高並行検証のため check_same_thread=False）
DATABASE_URL = "sqlite:///./cinema.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """テーブル作成 + シードデータ投入"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 映画データ
        movies_data = [
            {
                "title": "君の名は。 リバイバル",
                "duration": 107,
                "rating": 9.2,
                "description": "新海誠監督の傑作アニメーション。男女の運命的な出会いを描く。",
            },
            {
                "title": "千と千尋の神隠し",
                "duration": 125,
                "rating": 9.5,
                "description": "宮崎駿監督によるジブリ不朽の名作。",
            },
            {
                "title": "鬼滅の刃 無限城編",
                "duration": 140,
                "rating": 9.0,
                "description": "炭治郎たちが無限城で上弦の鬼と激闘を繰り広げる。",
            },
            {
                "title": "Dune: Part Three",
                "duration": 165,
                "rating": 8.8,
                "description": "ポール・アトレイデスの最終章、砂の惑星の運命が決まる。",
            },
        ]

        movies = []
        for m in movies_data:
            movie = Movie(**m)
            db.add(movie)
            movies.append(movie)
        db.commit()

        # 上映回データ（各映画3回上映）
        base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        halls = ["IMAX 1番ホール", "Dolby 2番ホール", "通常 3番ホール"]
        prices = [2200.0, 1800.0, 1500.0]

        for movie in movies:
            for i, (hall, price) in enumerate(zip(halls, prices)):
                showtime = Showtime(
                    movie_id=movie.id,
                    hall_name=hall,
                    start_time=base_time + timedelta(hours=2 + i * 3),
                    price=price,
                    total_seats=64,
                )
                db.add(showtime)
                db.flush()

                # 座席を作成（8行 x 8列）
                for row in range(1, 9):
                    for col in range(1, 9):
                        seat = Seat(
                            showtime_id=showtime.id,
                            row_num=row,
                            col_num=col,
                            is_booked=False,
                        )
                        db.add(seat)
        db.commit()
        print(f"✅ シードデータ投入完了: 映画{len(movies)}本、上映回{len(movies) * 3}回")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
