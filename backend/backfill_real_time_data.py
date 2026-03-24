#!/usr/bin/env python3
"""
回填 real_time_data 表中各指标的历史数据，从 2026-02-28 开始
"""
import sys
import os
import math
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()

from datetime import datetime, timezone, timedelta
from app.core.database import db

db.connect()
col = db.db["real_time_data"]

# 指标名称到 Yahoo Finance ticker 的映射
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

# 指标单位
UNITS = {
    "标普500":                "点",
    "纳斯达克指数":           "点",
    "道琼斯指数":             "点",
    "布伦特原油期货":         "美元/桶",
    "纽约原油期货":           "美元/桶",
    "纽约黄金":               "美元/盎司",
    "波动率指数VIX":          "点",
    "10年期国债收益率":        "%",
    "2年期国债收益率":        "%",
    "美元指数":               "点",
    "RBOB汽油价格":           "美元/加仑",
    "布油-WTI地缘溢价":       "美元/桶",
}

def _yfinance_history(ticker: str, start: str, end: str) -> list:
    """通过 Yahoo Finance v8 JSON API 获取历史数据"""
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
                history.append((dt, float(close)))
        return history
    except Exception as e:
        print(f"  警告: 获取 {ticker} 历史数据失败: {e}")
        return []

def main():
    start_date = "2026-02-28"
    end_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"正在获取 {start_date} ~ {end_date} 的历史数据...\n")
    
    # 获取所有 ticker 的历史数据
    ticker_history = {}
    
    for name, ticker in TICKERS.items():
        print(f"正在获取 {name} ({ticker}) ...")
        history = _yfinance_history(ticker, start_date, end_date)
        if history:
            ticker_history[name] = history
            print(f"  成功获取 {len(history)} 个数据点")
        else:
            print(f"  获取失败")
    
    # 插入或更新 real_time_data 表
    inserted = 0
    skipped = 0
    
    for name, history in ticker_history.items():
        for dt, value in history:
            # 检查该指标在该时间点附近是否已有数据
            existing = col.find_one({
                "name": name,
                "updated_at": {
                    "$gte": dt - timedelta(hours=12),
                    "$lte": dt + timedelta(hours=12)
                }
            })
            
            if existing:
                skipped += 1
                continue
            
            # 插入新记录
            doc = {
                "name": name,
                "value": round(value, 4),
                "unit": UNITS.get(name, ""),
                "updated_at": dt,
                "source": "Yahoo Finance (backfilled)",
                "_backfilled": True
            }
            col.insert_one(doc)
            inserted += 1
    
    print(f"\n完成: 插入 {inserted} 条, 跳过 {skipped} 条")
    
    # 计算并回填布油-WTI地缘溢价
    print("\n正在计算并回填布油-WTI地缘溢价...")
    brent_history = ticker_history.get("布伦特原油期货", [])
    wti_history = ticker_history.get("纽约原油期货", [])
    
    # 创建按日期索引的字典
    brent_by_date = {dt.date(): (dt, val) for dt, val in brent_history}
    wti_by_date = {dt.date(): (dt, val) for dt, val in wti_history}
    
    premium_inserted = 0
    premium_skipped = 0
    
    for date in set(brent_by_date.keys()) & set(wti_by_date.keys()):
        dt_brent, brent_val = brent_by_date[date]
        dt_wti, wti_val = wti_by_date[date]
        premium = brent_val - wti_val
        
        # 使用较晚的时间作为更新时间
        dt = max(dt_brent, dt_wti)
        
        # 检查是否已有数据
        existing = col.find_one({
            "name": "布油-WTI地缘溢价",
            "updated_at": {
                "$gte": dt - timedelta(hours=12),
                "$lte": dt + timedelta(hours=12)
            }
        })
        
        if existing:
            premium_skipped += 1
            continue
        
        doc = {
            "name": "布油-WTI地缘溢价",
            "value": round(premium, 4),
            "unit": UNITS.get("布油-WTI地缘溢价", ""),
            "updated_at": dt,
            "source": "Calculated (backfilled)",
            "_backfilled": True
        }
        col.insert_one(doc)
        premium_inserted += 1
    
    print(f"布油-WTI地缘溢价: 插入 {premium_inserted} 条, 跳过 {premium_skipped} 条")
    
    db.disconnect()

if __name__ == "__main__":
    main()
