#!/usr/bin/env python3
"""
回填 2026-02-28 至今的新增指标历史数据到 real_time_data 集合。
这样前端趋势图可以显示完整历史。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()

import yfinance as yf
from datetime import datetime, timezone, timedelta
from app.core.database import db

db.connect()
col = db.db["real_time_data"]

# 新增指标
TICKERS = [
    {"name": "美元指数",       "ticker": "DX-Y.NYB", "unit": "",         "source": "Yahoo Finance (DX-Y.NYB) backfill"},
    {"name": "美国汽油价格",   "ticker": "RB=F",    "unit": "美元/加仑", "source": "Yahoo Finance (RB=F) backfill"},
]

start = "2026-02-28"
end   = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

inserted = 0
skipped = 0

for info in TICKERS:
    name = info["name"]
    ticker = info["ticker"]
    print(f"\nFetching {name} ({ticker}) {start} ~ {end} ...")
    data = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    print(f"Got {len(data)} trading days")

    for date_idx, (date, row) in enumerate(data.iterrows()):
        close = float(row["Close"].iloc[0])
        if close is None or close != close:  # NaN check
            print(f"  {date.date()}: NaN, skipping")
            skipped += 1
            continue

        # 每天收盘时间 UTC 21:00 = 美东 16:00-17:00
        dt = datetime(date.year, date.month, date.day, 21, 0, 0, tzinfo=timezone.utc)

        # 检查是否已有这个时间点的数据
        existing = col.find_one({
            "name": name,
            "updated_at": {"$gte": dt - timedelta(minutes=30), "$lte": dt + timedelta(minutes=30)}
        })
        if existing:
            print(f"  {date.date()}: already exists, skipping")
            skipped += 1
            continue

        doc = {
            "name": name,
            "value": round(close, 4),
            "unit": info["unit"],
            "trend": "unknown",
            "source": info["source"],
            "updated_at": dt,
            "created_at": dt,
        }
        col.insert_one(doc)
        inserted += 1
        print(f"  {date.date()}: inserted {close:.4f}")

print(f"\n=== Done ===")
print(f"Total inserted: {inserted}")
print(f"Total skipped: {skipped}")
db.disconnect()
