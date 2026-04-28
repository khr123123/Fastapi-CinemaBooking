"""
Tkinter GUI クライアント
🎬 映画チケット予約システム
"""
import tkinter as tk
from tkinter import ttk, messagebox, font
import requests
from PIL import Image, ImageTk
import io
import threading
import uuid
from datetime import datetime

API_BASE = "http://127.0.0.1:8000/api"

# カラーテーマ（ダークモード）
COLORS = {
    "bg": "#1a1a2e",
    "panel": "#16213e",
    "accent": "#e94560",
    "accent_hover": "#ff5e7e",
    "text": "#eaeaea",
    "text_dim": "#a0a0b0",
    "available": "#4caf50",
    "locked": "#ff9800",
    "booked": "#555555",
    "selected": "#2196f3",
    "gold": "#ffd700",
}


class CinemaBookingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 映画チケット予約システム - Cinema Booking")
        self.root.geometry("1200x780")
        self.root.configure(bg=COLORS["bg"])

        # ユーザーセッション
        self.user_id = f"user_{uuid.uuid4().hex[:8]}"
        self.current_movie = None
        self.current_showtime = None
        self.selected_seats = set()  # seat_id のセット
        self.seat_buttons = {}  # seat_id -> button widget
        self.locked_seat_ids = set()  # 自分がロックしている座席

        self._setup_styles()
        self._build_ui()
        self._load_movies()
        self._start_seat_polling()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            padding=[20, 10],
            font=("Helvetica", 11, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", "white")],
        )
        style.configure("TCombobox", fieldbackground=COLORS["panel"], background=COLORS["panel"])

    def _build_ui(self):
        # ヘッダー
        header = tk.Frame(self.root, bg=COLORS["accent"], height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="🎬 CINEMA BOOKING SYSTEM",
            font=("Helvetica", 22, "bold"),
            bg=COLORS["accent"],
            fg="white",
        )
        title.pack(side=tk.LEFT, padx=30, pady=15)

        self.user_label = tk.Label(
            header,
            text=f"👤 ユーザー: {self.user_id}",
            font=("Helvetica", 11),
            bg=COLORS["accent"],
            fg="white",
        )
        self.user_label.pack(side=tk.RIGHT, padx=30)

        # タブ
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_book = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.tab_orders = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.tab_stats = tk.Frame(self.notebook, bg=COLORS["bg"])

        self.notebook.add(self.tab_book, text="🎟️  予約する")
        self.notebook.add(self.tab_orders, text="📋 注文履歴")
        self.notebook.add(self.tab_stats, text="📊 システム統計")

        self._build_booking_tab()
        self._build_orders_tab()
        self._build_stats_tab()

        # ステータスバー
        self.status_bar = tk.Label(
            self.root,
            text="✅ 準備完了",
            bg=COLORS["panel"],
            fg=COLORS["text_dim"],
            anchor=tk.W,
            padx=15,
            font=("Helvetica", 9),
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_booking_tab(self):
        # 左パネル：映画一覧
        left = tk.Frame(self.tab_book, bg=COLORS["panel"], width=280)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(
            left, text="🎥 上映中の映画",
            font=("Helvetica", 14, "bold"),
            bg=COLORS["panel"], fg=COLORS["gold"],
        ).pack(pady=15)

        self.movie_listbox = tk.Listbox(
            left,
            bg=COLORS["bg"], fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="white",
            font=("Helvetica", 11),
            borderwidth=0, highlightthickness=0,
            activestyle="none",
        )
        self.movie_listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        self.movie_listbox.bind("<<ListboxSelect>>", self._on_movie_select)

        self.poster_label = tk.Label(left, bg=COLORS["panel"])
        self.poster_label.pack(pady=10)

        tk.Button(
            left, text="🔄 更新",
            command=self._load_movies,
            bg=COLORS["accent"], fg="white",
            font=("Helvetica", 10, "bold"),
            relief=tk.RAISED, bd=2, cursor="hand2",
        ).pack(fill=tk.X, padx=15, pady=(0, 15))

        # 中央パネル：座席選択
        center = tk.Frame(self.tab_book, bg=COLORS["bg"])
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 上映回選択
        showtime_frame = tk.Frame(center, bg=COLORS["panel"])
        showtime_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            showtime_frame, text="📅 上映回:",
            bg=COLORS["panel"], fg=COLORS["text"],
            font=("Helvetica", 11, "bold"),
        ).pack(side=tk.LEFT, padx=15, pady=10)

        self.showtime_var = tk.StringVar()
        self.showtime_combo = ttk.Combobox(
            showtime_frame, textvariable=self.showtime_var,
            state="readonly", width=60, font=("Helvetica", 10),
        )
        self.showtime_combo.pack(side=tk.LEFT, padx=10, pady=10)
        self.showtime_combo.bind("<<ComboboxSelected>>", self._on_showtime_select)

        # スクリーン表示
        screen_frame = tk.Frame(center, bg=COLORS["bg"])
        screen_frame.pack(fill=tk.X, pady=10)
        tk.Label(
            screen_frame, text="━━━━━━━━━ 🎬 SCREEN 🎬 ━━━━━━━━━",
            bg=COLORS["bg"], fg=COLORS["gold"],
            font=("Helvetica", 14, "bold"),
        ).pack()

        # 座席グリッド
        self.seat_frame = tk.Frame(center, bg=COLORS["bg"])
        self.seat_frame.pack(pady=20)

        # 凡例
        legend = tk.Frame(center, bg=COLORS["bg"])
        legend.pack(pady=10)
        for color, text in [
            (COLORS["available"], "🟢 空席"),
            (COLORS["selected"], "🔵 選択中"),
            (COLORS["locked"], "🟡 ロック中"),
            (COLORS["booked"], "⚫ 予約済"),
        ]:
            f = tk.Frame(legend, bg=COLORS["bg"])
            f.pack(side=tk.LEFT, padx=15)
            tk.Label(f, text="●", fg=color, bg=COLORS["bg"], font=("Helvetica", 16)).pack(side=tk.LEFT)
            tk.Label(f, text=text, bg=COLORS["bg"], fg=COLORS["text"], font=("Helvetica", 10)).pack(side=tk.LEFT)

        # 右パネル：注文情報
        right = tk.Frame(self.tab_book, bg=COLORS["panel"], width=260)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(
            right, text="🛒 注文サマリー",
            font=("Helvetica", 14, "bold"),
            bg=COLORS["panel"], fg=COLORS["gold"],
        ).pack(pady=15)

        self.summary_text = tk.Text(
            right, height=20, width=28,
            bg=COLORS["bg"], fg=COLORS["text"],
            font=("Helvetica", 10),
            borderwidth=0, padx=10, pady=10,
            wrap=tk.WORD,
        )
        self.summary_text.pack(padx=15, pady=10, fill=tk.BOTH, expand=True)
        self.summary_text.config(state=tk.DISABLED)

        self.btn_lock = tk.Button(
            right, text="🔒 座席をロック",
            command=self._lock_seats,
            bg=COLORS["locked"], fg="white",
            font=("Helvetica", 11, "bold"),
            relief=tk.RAISED, bd=2, cursor="hand2", state=tk.DISABLED,
        )
        self.btn_lock.pack(fill=tk.X, padx=15, pady=5)

        self.btn_pay = tk.Button(
            right, text="💳 支払って予約確定",
            command=self._create_order,
            bg=COLORS["accent"], fg="white",
            font=("Helvetica", 11, "bold"),
            relief=tk.RAISED, bd=2, cursor="hand2", state=tk.DISABLED,
        )
        self.btn_pay.pack(fill=tk.X, padx=15, pady=5)

        self.btn_release = tk.Button(
            right, text="❌ ロック解除",
            command=self._release_seats,
            bg=COLORS["text_dim"], fg="white",
            font=("Helvetica", 10),
            relief=tk.RAISED, bd=2, cursor="hand2", state=tk.DISABLED,
        )
        self.btn_release.pack(fill=tk.X, padx=15, pady=5)

    def _build_orders_tab(self):
        top = tk.Frame(self.tab_orders, bg=COLORS["bg"])
        top.pack(fill=tk.X, pady=10)

        tk.Label(
            top, text="📋 マイ注文履歴",
            font=("Helvetica", 16, "bold"),
            bg=COLORS["bg"], fg=COLORS["gold"],
        ).pack(side=tk.LEFT, padx=15)

        tk.Button(
            top, text="🔄 更新",
            command=self._load_orders,
            bg=COLORS["accent"], fg="white",
            font=("Helvetica", 10, "bold"),
            relief=tk.RAISED, bd=2, cursor="hand2",
        ).pack(side=tk.RIGHT, padx=15)

        columns = ("注文番号", "上映回ID", "座席", "金額", "状態", "日時")
        self.orders_tree = ttk.Treeview(
            self.tab_orders, columns=columns, show="headings", height=20
        )
        for col in columns:
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=150)
        self.orders_tree.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

    def _build_stats_tab(self):
        tk.Label(
            self.tab_stats, text="📊 システム統計（リアルタイム）",
            font=("Helvetica", 16, "bold"),
            bg=COLORS["bg"], fg=COLORS["gold"],
        ).pack(pady=20)

        self.stats_text = tk.Text(
            self.tab_stats, height=20, width=80,
            bg=COLORS["panel"], fg=COLORS["text"],
            font=("Consolas", 12),
            borderwidth=0, padx=20, pady=20,
        )
        self.stats_text.pack(padx=20, pady=10)

        tk.Button(
            self.tab_stats, text="🔄 統計を更新",
            command=self._load_stats,
            bg=COLORS["accent"], fg="white",
            font=("Helvetica", 11, "bold"),
            relief=tk.RAISED, bd=2, cursor="hand2", padx=20, pady=8,
        ).pack(pady=10)

    # ========== API 呼び出し ==========

    def _set_status(self, msg, color=None):
        self.status_bar.config(text=msg, fg=color or COLORS["text_dim"])

    def _api_get(self, path):
        try:
            r = requests.get(f"{API_BASE}{path}", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            messagebox.showerror("APIエラー", f"接続失敗: {e}\n\nサーバーが起動しているか確認してください。")
            return None

    def _api_post(self, path, data):
        try:
            r = requests.post(f"{API_BASE}{path}", json=data, timeout=5)
            return r.status_code, r.json()
        except Exception as e:
            messagebox.showerror("APIエラー", f"接続失敗: {e}")
            return 500, {"detail": str(e)}

    def _load_movies(self):
        movies = self._api_get("/movies")
        if not movies:
            return
        self.movies = movies
        self.movie_listbox.delete(0, tk.END)
        for m in movies:
            self.movie_listbox.insert(
                tk.END, f"  ⭐{m['rating']}  {m['title']}  ({m['duration']}分)"
            )
        self._set_status(f"✅ {len(movies)}本の映画を読み込みました")

    def _on_movie_select(self, event):
        sel = self.movie_listbox.curselection()
        if not sel:
            return
        self.current_movie = self.movies[sel[0]]
        showtimes = self._api_get(f"/showtimes/{self.current_movie['id']}")
        if not showtimes:
            return
        self.showtimes = showtimes
        values = []
        for st in showtimes:
            dt = datetime.fromisoformat(st["start_time"])
            values.append(
                f"{dt.strftime('%m/%d %H:%M')} | {st['hall_name']} | ¥{int(st['price'])} | 残{st['available_seats']}席"
            )
        self.showtime_combo["values"] = values
        if values:
            self.showtime_combo.current(0)
            self._on_showtime_select(None)

    def _on_showtime_select(self, event):
        idx = self.showtime_combo.current()
        if idx < 0:
            return
        self.current_showtime = self.showtimes[idx]
        self.selected_seats.clear()
        self._load_seats()
        self._update_summary()


    def _start_seat_polling(self):
        self._refresh_seats()
        self.root.after(3000, self._start_seat_polling)

    def _refresh_seats(self):
        if not self.current_showtime:
            return
        # Only fetch status if not creating new buttons to avoid blinking
        seats = self._api_get(f"/seats/{self.current_showtime['id']}")
        if not seats:
            return
        for seat in seats:
            sid = seat["id"]
            if sid in self.seat_buttons:
                btn = self.seat_buttons[sid]
                # Do not change if selected by me
                if sid in self.selected_seats:
                    continue
                if seat["status"] == "booked":
                    btn.config(bg=COLORS["booked"], state=tk.DISABLED)
                elif seat["status"] == "locked":
                    if sid in self.locked_seat_ids:
                        btn.config(bg=COLORS["selected"], state=tk.NORMAL)
                    else:
                        btn.config(bg=COLORS["locked"], state=tk.DISABLED)
                else:
                    btn.config(bg=COLORS["available"], state=tk.NORMAL)
    def _load_seats(self):
        if not self.current_showtime:
            return
        seats = self._api_get(f"/seats/{self.current_showtime['id']}")
        if seats is None:
            return

        # 既存ボタン削除
        for w in self.seat_frame.winfo_children():
            w.destroy()
        self.seat_buttons.clear()

        # 8x8グリッド
        for seat in seats:
            row = seat["row_num"]
            col = seat["col_num"]
            sid = seat["id"]

            if seat["status"] == "booked":
                color = COLORS["booked"]
                state = tk.DISABLED
            elif seat["status"] == "locked":
                if sid in self.locked_seat_ids:
                    color = COLORS["selected"]
                    state = tk.NORMAL
                else:
                    color = COLORS["locked"]
                    state = tk.DISABLED
            else:
                color = COLORS["available"]
                state = tk.NORMAL

            btn = tk.Button(
                self.seat_frame,
                text=f"{chr(64+row)}{col}",
                width=4, height=2,
                bg=color, fg="white",
                font=("Helvetica", 9, "bold"),
                relief=tk.RAISED, bd=2, cursor="hand2",
                state=state,
                command=lambda s=sid: self._toggle_seat(s),
            )
            btn.grid(row=row, column=col, padx=5, pady=(abs(col - 4.5)*10, 2))
            # 中央通路
            if col == 4:
                tk.Frame(self.seat_frame, width=20, bg=COLORS["bg"]).grid(row=row, column=99)
            self.seat_buttons[sid] = btn

    def _toggle_seat(self, seat_id):
        btn = self.seat_buttons[seat_id]
        if seat_id in self.selected_seats:
            self.selected_seats.remove(seat_id)
            btn.config(bg=COLORS["available"])
        else:
            if len(self.selected_seats) >= 6:
                messagebox.showwarning("注意", "1回の予約は最大6席までです")
                return
            self.selected_seats.add(seat_id)
            btn.config(bg=COLORS["selected"])
        self._update_summary()

    def _update_summary(self):
        self.summary_text.config(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)

        if not self.current_movie or not self.current_showtime:
            self.summary_text.insert(tk.END, "映画と上映回を選択してください")
            self.summary_text.config(state=tk.DISABLED)
            return

        info = f"🎬 {self.current_movie['title']}\n"
        info += f"━━━━━━━━━━━━━━━━\n"
        dt = datetime.fromisoformat(self.current_showtime["start_time"])
        info += f"📅 {dt.strftime('%Y/%m/%d %H:%M')}\n"
        info += f"🏛️ {self.current_showtime['hall_name']}\n"
        info += f"💴 単価: ¥{int(self.current_showtime['price'])}\n\n"

        if self.selected_seats:
            info += f"🎟️ 選択席数: {len(self.selected_seats)}席\n"
            info += f"座席ID: {sorted(self.selected_seats)}\n\n"
            total = self.current_showtime["price"] * len(self.selected_seats)
            info += f"━━━━━━━━━━━━━━━━\n"
            info += f"💰 合計: ¥{int(total)}\n"
            self.btn_lock.config(state=tk.NORMAL)
        else:
            info += "座席を選択してください"
            self.btn_lock.config(state=tk.DISABLED)

        if self.locked_seat_ids:
            info += f"\n\n🔒 ロック中: {len(self.locked_seat_ids)}席"

        self.summary_text.insert(tk.END, info)
        self.summary_text.config(state=tk.DISABLED)

    def _lock_seats(self):
        if not self.selected_seats:
            return
        data = {
            "showtime_id": self.current_showtime["id"],
            "seat_ids": list(self.selected_seats),
            "user_id": self.user_id,
        }
        self._set_status("🔄 座席ロック中...")
        code, result = self._api_post("/seats/lock", data)

        if result.get("success"):
            self.locked_seat_ids.update(self.selected_seats)
            messagebox.showinfo(
                "✅ ロック成功",
                f"{result['message']}\n\n5分以内に決済を完了してください。"
            )
            self.btn_pay.config(state=tk.NORMAL)
            self.btn_release.config(state=tk.NORMAL)
            self._set_status(f"🔒 {len(self.selected_seats)}席をロックしました", COLORS["locked"])
        else:
            messagebox.showerror(
                "❌ ロック失敗",
                f"{result.get('message', '不明なエラー')}\n\n失敗座席: {result.get('failed_seats', [])}"
            )
            self._load_seats()

    def _create_order(self):
        if not self.locked_seat_ids:
            return
        data = {
            "showtime_id": self.current_showtime["id"],
            "seat_ids": list(self.locked_seat_ids),
            "user_id": self.user_id,
        }
        self._set_status("💳 決済処理中...")
        code, result = self._api_post("/orders", data)

        if code == 200:
            total = result["total_price"]
            messagebox.showinfo(
                "🎉 予約完了！",
                f"注文番号: {result['order_no']}\n"
                f"座席数: {len(self.locked_seat_ids)}席\n"
                f"合計金額: ¥{int(total)}\n\n"
                f"上映時刻にお越しください！"
            )
            self.locked_seat_ids.clear()
            self.selected_seats.clear()
            self.btn_pay.config(state=tk.DISABLED)
            self.btn_release.config(state=tk.DISABLED)
            self._load_seats()
            self._update_summary()
            self._set_status("✅ 予約完了", COLORS["available"])
        else:
            messagebox.showerror("決済失敗", result.get("detail", "不明なエラー"))

    def _release_seats(self):
        if not self.locked_seat_ids:
            return
        data = {
            "showtime_id": self.current_showtime["id"],
            "seat_ids": list(self.locked_seat_ids),
            "user_id": self.user_id,
        }
        self._api_post("/seats/release", data)
        self.locked_seat_ids.clear()
        self.selected_seats.clear()
        self.btn_pay.config(state=tk.DISABLED)
        self.btn_release.config(state=tk.DISABLED)
        self._load_seats()
        self._update_summary()
        self._set_status("ロックを解除しました")

    def _load_orders(self):
        orders = self._api_get(f"/orders/{self.user_id}")
        if orders is None:
            return
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        for o in orders:
            dt = datetime.fromisoformat(o["created_at"]).strftime("%Y/%m/%d %H:%M")
            self.orders_tree.insert("", tk.END, values=(
                o["order_no"], o["showtime_id"], o["seat_ids"],
                f"¥{int(o['total_price'])}", o["status"], dt,
            ))
        self._set_status(f"📋 {len(orders)}件の注文を読み込みました")

    def _load_stats(self):
        stats = self._api_get("/stats")
        if not stats:
            return
        ls = stats["lock_stats"]
        success_rate = (ls['lock_success']/max(ls['lock_attempts'],1)*100)
        text = f"""
✨🌟✨ リアルタイム・シネマダッシュボード ✨🌟✨
===================================================

    📊 【 ロック統計（メモリ層） 】
    ---------------------------------------------
       ▶ 総ロック試行数:    {ls['lock_attempts']:>8} 回
       ▶ ロック成功:        {ls['lock_success']:>8} 回
       ▶ 競合（衝突）:      {ls['lock_conflicts']:>8} 回
       ▶ ロック解放:        {ls['lock_released']:>8} 回
       ▶ 現在アクティブ:    {stats['active_locks']:>8} 席

    💰 【 ビジネス統計（DB層） 】
    ---------------------------------------------
       ▶ 総注文数:          {stats['total_orders']:>8} 件
       ▶ 総売上:          ¥{int(stats['total_revenue']):>8}

    📈 【 パフォーマンス 】
    ---------------------------------------------
       ▶ ロック成功率:      {success_rate:>8.1f} %

===================================================
"""
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.insert(tk.END, text)
        self.stats_text.configure(font=("Courier New", 14, "bold"))



def main():
    root = tk.Tk()
    app = CinemaBookingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()