#!/usr/bin/env python3
"""
回填 2026-02-28 至今的历史市场数据到 factor_scores 集合。
用于回归分析模块的 X 数据。
使用与 real_time_ingestor 一致的指标名称。
"""
import sys, os
import math
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()

from datetime import datetime, timezone, timedelta
from app.core.database import db

db.connect()
col = db.db["factor_scores"]

TICKERS = {
    "标普500":                "^GSPC",
    "纳斯达克指数":           "^IXIC",
    "道琼斯指数":             "^DJI",
    "布伦特原油期货":         "BZ=F",
    "纽约原油期货":           "CL=F",
    "纽约黄金":               "GC=F",
    "波动率指数VIX":          "^VIX",
    "10年期国债收益率":        "^TNX",
    "2年期国债收益率":        "^IRX",
    "美元指数":               "DX-Y.NYB",
    "RBOB汽油价格":           "RB=F",
}

# 需要计算对数收益率的价格型变量
PRICE_TICKERS = ["标普500", "布伦特原油期货", "纽约原油期货", "纽约黄金"]

def _yfinance_history(ticker: str, start: str, end: str) -> list:
    """通过 Yahoo Finance v8 JSON API 获取历史数据，无需第三方库。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 将日期字符串转换为时间戳
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    
    params = {
        "interval": "1d",
        "period1": start_ts,
        "period2": end_ts,
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        
        # 转换为日期和价格
        history = []
        for ts, close in zip(timestamps, closes):
            if close is not None:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                history.append((dt.date(), float(close)))
        return history
    except Exception as e:
        print(f"  警告: 获取 {ticker} 历史数据失败: {e}")
        return []

start = "2026-02-28"
end   = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

print(f"Fetching {start} ~ {end} ...")

# 获取所有 ticker 的历史数据
ticker_history = {}
all_dates = set()

for name, ticker in TICKERS.items():
    print(f"  正在获取 {name} ({ticker}) ...")
    history = _yfinance_history(ticker, start, end)
    if history:
        ticker_history[name] = {d: p for d, p in history}
        for d, _ in history:
            all_dates.add(d)
        print(f"    成功获取 {len(history)} 个数据点")
    else:
        print(f"    获取失败")

if not all_dates:
    print("错误: 没有获取到任何历史数据")
    sys.exit(1)

# 按日期排序
sorted_dates = sorted(all_dates)
print(f"\n共获取 {len(sorted_dates)} 个交易日数据")

inserted = skipped = updated = 0
prev_values = {}

# 遍历每个日期
for idx, date in enumerate(sorted_dates):
    raw = {}
    
    # 基础价格指标
    for name in TICKERS.keys():
        if name in ticker_history and date in ticker_history[name]:
            raw[name] = round(ticker_history[name][date], 4)
    
    # 计算对数收益率：log(pt / pt-1)
    if idx > 0:
        prev_date = sorted_dates[idx - 1]
        for name in PRICE_TICKERS:
            if name in ticker_history:
                pt = ticker_history[name].get(date)
                pt_prev = ticker_history[name].get(prev_date)
                if pt is not None and pt_prev is not None and pt > 0 and pt_prev > 0:
                    try:
                        ret = math.log(pt / pt_prev)
                        raw[f"{name}收益率"] = round(ret, 6)
                    except Exception:
                        pass
    
    # 计算布油-WTI地缘溢价
    if "布伦特原油期货" in raw and "纽约原油期货" in raw:
        raw["布油-WTI地缘溢价"] = round(raw["布伦特原油期货"] - raw["纽约原油期货"], 4)
    
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
            print(f"  {date} updated: +{len(existing_raw) - original_len} indicators: {new_keys}")
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
    print(f"  {date} inserted: {list(raw.keys())}")

print(f"\nDone: inserted={inserted}, updated={updated}, skipped={skipped}")
db.disconnect()
