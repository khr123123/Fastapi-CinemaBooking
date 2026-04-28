"""
FastAPI サーバー起動スクリプト
使い方: python run_server.py
"""
import os

import uvicorn

from database import init_db

if __name__ == "__main__":
    if not os.path.exists("cinema.db"):
        print("📦 データベース初期化中...")
        init_db()
    print("🚀 サーバー起動: http://127.0.0.1:8000")
    print("📖 API ドキュメント: http://127.0.0.1:8000/docs")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
    )
