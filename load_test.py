"""
高並行負荷テスト
正しく1人だけ成功し、残りは失敗するか検証
"""
import asyncio
import aiohttp
import time
from collections import Counter

API_BASE = "http://127.0.0.1:8000/api"


async def get_showtime_seats(session, showtime_id):
    """指定上映回の座席IDリストを取得"""
    async with session.get(f"{API_BASE}/seats/{showtime_id}") as r:
        seats = await r.json()
        available = [s["id"] for s in seats if s["status"] == "available"]
        return available


async def try_lock(session, user_id, showtime_id, seat_ids):
    try:
        async with session.post(
            f"{API_BASE}/seats/lock",
            json={
                "showtime_id": showtime_id,
                "seat_ids": seat_ids,
                "user_id": user_id,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            return user_id, data.get("success", False), data.get("message", "")
    except Exception as e:
        return user_id, False, f"ERR: {e}"


async def release(session, user_id, showtime_id, seat_ids):
    async with session.post(
        f"{API_BASE}/seats/release",
        json={"showtime_id": showtime_id, "seat_ids": seat_ids, "user_id": user_id},
    ) as r:
        return await r.json()


async def test_concurrent_lock(num_users=50, showtime_id=1):
    """シナリオ1: 同じ座席への殺到"""
    print(f"\n{'='*60}")
    print(f"🔥 シナリオ1: 高並行ロックテスト（同じ座席への殺到）")
    print(f"{'='*60}")

    async with aiohttp.ClientSession() as session:
        seats = await get_showtime_seats(session, showtime_id)
        target_seats = seats[:2]  # 最初の2席を全員が狙う
        print(f"  並行ユーザー数: {num_users}")
        print(f"  対象座席ID: {target_seats}")
        print(f"  期待結果: 1人成功、{num_users-1}人失敗\n")

        start = time.time()
        tasks = [
            try_lock(session, f"rush_user_{i}", showtime_id, target_seats)
            for i in range(num_users)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        successes = [r for r in results if r[1]]
        failures = [r for r in results if not r[1]]

        print(f"  ⏱️  経過時間: {elapsed*1000:.1f} ms")
        print(f"  ✅ 成功: {len(successes)} 人")
        print(f"  ❌ 失敗: {len(failures)} 人")
        print(f"  📊 RPS: {num_users/elapsed:.1f} req/sec")

        if successes:
            print(f"  🏆 勝者: {successes[0][0]}")

        result_ok = len(successes) == 1
        print(f"\n  {'✅ テスト合格' if result_ok else '❌ テスト失敗'}: 並行制御は{'正しく' if result_ok else '誤って'}動作\n")

        # クリーンアップ
        if successes:
            await release(session, successes[0][0], showtime_id, target_seats)

        return result_ok


async def test_full_booking_flow(num_users=20, showtime_id=2):
    """シナリオ2: 異なる座席への並行注文"""
    print(f"{'='*60}")
    print(f"🎯 シナリオ2: 完全予約フロー並行テスト（異なる座席）")
    print(f"{'='*60}")

    async def book_flow(session, user_id, seat_id):
        # ロック取得
        async with session.post(
            f"{API_BASE}/seats/lock",
            json={"showtime_id": showtime_id, "seat_ids": [seat_id], "user_id": user_id},
        ) as r:
            lock_result = await r.json()
            if not lock_result.get("success"):
                return user_id, "lock_failed"

        # 注文作成
        async with session.post(
            f"{API_BASE}/orders",
            json={"showtime_id": showtime_id, "seat_ids": [seat_id], "user_id": user_id},
        ) as r:
            if r.status == 200:
                return user_id, "success"
            return user_id, f"order_failed_{r.status}"

    async with aiohttp.ClientSession() as session:
        seats = await get_showtime_seats(session, showtime_id)
        target_seats = seats[:num_users]
        print(f"  ユーザー数: {num_users}")
        print(f"  各自が異なる座席を予約\n")

        start = time.time()
        tasks = [
            book_flow(session, f"flow_user_{i}", target_seats[i])
            for i in range(num_users)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

    counter = Counter(r[1] for r in results)
    print(f"  ⏱️  経過時間: {elapsed:.2f} 秒")
    for status, count in counter.items():
        emoji = "✅" if status == "success" else "❌"
        print(f"  {emoji} {status}: {count}人")
    print(f"  📊 スループット: {num_users/elapsed:.1f} 注文/秒\n")


async def main():
    await test_concurrent_lock(num_users=50, showtime_id=1)
    await test_full_booking_flow(num_users=20, showtime_id=2)

    # 最終統計
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/stats") as r:
            stats = await r.json()
            print(f"{'='*60}")
            print(f"📈 最終システム統計")
            print(f"{'='*60}")
            for k, v in stats["lock_stats"].items():
                print(f"  {k}: {v}")
            print(f"  total_orders: {stats['total_orders']}")
            print(f"  total_revenue: ¥{int(stats['total_revenue'])}")
            print(f"  active_locks: {stats['active_locks']}")


if __name__ == "__main__":
    asyncio.run(main())