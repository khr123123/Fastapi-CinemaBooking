"""
座席ロック管理サービス
高並行制御の核心モジュール
- メモリ内での原子的ロック取得（asyncio.Lock）
- TTL付き一時ロック（自動解放）
- Redis風の挙動をPythonで実装
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Set, List, Tuple


@dataclass
class SeatLockInfo:
    user_id: str
    expires_at: float  # Unix timestamp


class SeatLockManager:
    """
    座席ロック管理（シングルトン）

    特徴:
    1. グローバル asyncio.Lock で原子性を保証
    2. 一括ロック取得（all-or-nothing）
    3. TTL自動失効
    4. ユーザー単位の保持座席追跡
    """

    def __init__(self, lock_ttl: int = 300):
        self._locks: Dict[Tuple[int, int], SeatLockInfo] = {}  # (showtime_id, seat_id) -> info
        self._user_locks: Dict[str, Set[Tuple[int, int]]] = {}  # user_id -> set of keys
        self._global_lock = asyncio.Lock()
        self.lock_ttl = lock_ttl  # 秒
        # 統計情報
        self.stats = {
            "lock_attempts": 0,
            "lock_success": 0,
            "lock_conflicts": 0,
            "lock_released": 0,
        }

    async def _cleanup_expired(self):
        """期限切れロックを除去（内部呼び出しのみ、global_lock取得済み前提）"""
        now = time.time()
        expired_keys = [k for k, v in self._locks.items() if v.expires_at < now]
        for key in expired_keys:
            info = self._locks.pop(key)
            if info.user_id in self._user_locks:
                self._user_locks[info.user_id].discard(key)

    async def try_lock_seats(
            self, showtime_id: int, seat_ids: List[int], user_id: str
    ) -> Tuple[bool, List[int], List[int]]:
        """
        座席を一括でロックする（all-or-nothing）

        Returns:
            (success, locked_seat_ids, conflicted_seat_ids)
        """
        async with self._global_lock:
            self.stats["lock_attempts"] += 1
            await self._cleanup_expired()

            now = time.time()
            keys = [(showtime_id, sid) for sid in seat_ids]

            # 競合チェック
            conflicts = []
            for key, sid in zip(keys, seat_ids):
                if key in self._locks:
                    info = self._locks[key]
                    # 同じユーザーが既にロック済みなら許可
                    if info.user_id != user_id and info.expires_at > now:
                        conflicts.append(sid)

            if conflicts:
                self.stats["lock_conflicts"] += 1
                return False, [], conflicts

            # 全席ロック取得
            expires = now + self.lock_ttl
            for key in keys:
                self._locks[key] = SeatLockInfo(user_id=user_id, expires_at=expires)
            self._user_locks.setdefault(user_id, set()).update(keys)

            self.stats["lock_success"] += 1
            return True, seat_ids, []

    async def release_seats(
            self, showtime_id: int, seat_ids: List[int], user_id: str
    ) -> int:
        """
        ユーザーが保持しているロックを解放
        Returns: 解放できた座席数
        """
        async with self._global_lock:
            released = 0
            for sid in seat_ids:
                key = (showtime_id, sid)
                if key in self._locks and self._locks[key].user_id == user_id:
                    del self._locks[key]
                    released += 1
            if user_id in self._user_locks:
                self._user_locks[user_id] -= {(showtime_id, s) for s in seat_ids}
            self.stats["lock_released"] += released
            return released

    async def confirm_seats(
            self, showtime_id: int, seat_ids: List[int], user_id: str
    ) -> bool:
        """
        ロック確認後、確定（注文成立時に呼ばれる）
        ロックを保持し続けて、DB書き込み完了後に release を呼ぶ想定
        """
        async with self._global_lock:
            now = time.time()
            for sid in seat_ids:
                key = (showtime_id, sid)
                info = self._locks.get(key)
                if not info or info.user_id != user_id or info.expires_at < now:
                    return False
            return True

    async def get_locked_seats(self, showtime_id: int) -> Dict[int, str]:
        """指定上映回のロック中座席情報を取得 (seat_id -> user_id)"""
        async with self._global_lock:
            await self._cleanup_expired()
            return {
                sid: info.user_id
                for (st_id, sid), info in self._locks.items()
                if st_id == showtime_id
            }

    def get_stats(self) -> dict:
        return dict(self.stats)


# シングルトンインスタンス
seat_lock_manager = SeatLockManager(lock_ttl=300)
