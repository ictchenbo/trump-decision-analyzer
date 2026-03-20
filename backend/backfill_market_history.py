#!/usr/bin/env python3
"""
回填 2026-02-28 至今的历史市场数据到 factor_scores 集合。
用于回归分析模块的 X 数据。
"""
import sys, os
import math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()

import yfinance as yf
from datetime import datetime, timezone, timedelta
from app.core.database import db

db.connect()
col = db.db["factor_scores"]

TICKERS = {
    "标普500":        "^GSPC",
    "纳斯达克":       "^IXIC",
    "道琼斯":         "^DJI",
    "布伦特原油":     "BZ=F",
    "WTI原油":       "CL=F",
    "黄金价格":       "GC=F",
    "VIX指数":        "^VIX",
    "美国10年期国债":  "^TNX",
    "美国2年期国债":  "^IRX",
}

# 需要计算对数收益率的价格型变量
PRICE_TICKERS = ["标普500", "布伦特原油", "WTI原油", "黄金价格"]

start = "2026-02-28"
end   = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

print(f"Fetching {start} ~ {end} ...")
data = yf.download(list(TICKERS.values()), start=start, end=end, auto_adjust=True, progress=False)

# data["Close"] is a DataFrame: index=date, columns=ticker symbols
close = data["Close"]
print(f"Got {len(close)} trading days")
print(close.head())

# 保存所有日期的价格用于计算收益率
all_dates = list(close.index)
all_rows = [row for _, row in close.iterrows()]

inserted = skipped = updated = 0

# 遍历每个日期，计算价格和收益率
for idx, (date, row) in enumerate(zip(all_dates, all_rows)):
    raw = {}
    for cn, ticker in TICKERS.items():
        v = row.get(ticker)
        if v is not None and not (hasattr(v, '__class__') and v.__class__.__name__ == 'float' and str(v) == 'nan'):
            try:
                fv = float(v)
                if fv == fv:  # NaN check
                    raw[cn] = round(fv, 4)
            except Exception:
                pass

    # 计算对数收益率：log(pt / pt-1)
    if idx > 0:
        prev_row = all_rows[idx - 1]
        for cn in PRICE_TICKERS:
            ticker = TICKERS.get(cn)
            if not ticker:
                continue
            pt = row.get(ticker)
            pt_prev = prev_row.get(ticker)
            if pt is not None and pt_prev is not None and pt > 0 and pt_prev > 0:
                try:
                    fpt = float(pt)
                    fpt_prev = float(pt_prev)
                    if fpt == fpt and fpt_prev == fpt_prev:
                        ret = math.log(fpt / fpt_prev)
                        raw[f"{cn}收益率"] = round(ret, 6)
                except Exception:
                    pass

    if not raw:
        continue

    dt = datetime(date.year, date.month, date.day, 21, 0, 0, tzinfo=timezone.utc)

    # 检查当天是否已有数据
    existing = col.find_one({
        "computed_at": {"$gte": datetime(date.year, date.month, date.day, tzinfo=timezone.utc),
                        "$lt":  datetime(date.year, date.month, date.day, tzinfo=timezone.utc) + timedelta(days=1)}
    })
    if existing:
        # 如果已存在，合并新指标到现有 raw_indicators
        existing_raw = existing.get("raw_indicators", {})
        original_len = len(existing_raw)
        existing_raw.update(raw)
        if len(existing_raw) > original_len:
            # 更新文档
            col.update_one(
                {"_id": existing["_id"]},
                {"$set": {"raw_indicators": existing_raw}}
            )
            updated += 1
            new_keys = [k for k in raw if k not in existing_raw]
            print(f"  {date.date()} updated: +{len(existing_raw) - original_len} indicators: {new_keys}")
        else:
            skipped += 1
        continue

    doc = {
        "computed_at": dt,
        "raw_indicators": raw,
        "factor_scores": {},
        "composite_index": None,
        "weights": {},
        "_backfilled": True,
    }
    col.insert_one(doc)
    inserted += 1
    print(f"  {date.date()} inserted: {list(raw.keys())}")

print(f"\nDone: inserted={inserted}, updated={updated}, skipped={skipped}")
db.disconnect()
