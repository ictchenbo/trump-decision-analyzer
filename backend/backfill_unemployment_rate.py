#!/usr/bin/env python3
"""
失业率历史数据回填脚本

从 FRED API 获取最近 24 个月的 UNRATE 数据，
写入 real_time_data 集合，用于前端趋势图展示。
"""

import os
import sys
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.database import db

load_dotenv()

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

if not FRED_API_KEY:
    print("错误：缺少 FRED_API_KEY 环境变量")
    sys.exit(1)

# 连接数据库
db.connect()
collection = db.db["real_time_data"]

# 从 FRED 获取最近 24 个月的 UNRATE 数据
print("正在从 FRED API 获取 UNRATE 历史数据...")
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "UNRATE",
    "api_key": FRED_API_KEY,
    "file_type": "json",
    "sort_order": "desc",
    "limit": 24,
}

resp = requests.get(url, params=params, timeout=15)
resp.raise_for_status()
observations = resp.json()["observations"]

# 过滤掉无效值，按时间正序排列
valid_obs = [o for o in observations if o["value"] != "."]
valid_obs.reverse()  # 从旧到新排序

if len(valid_obs) == 0:
    print("错误：FRED 数据不足")
    sys.exit(1)

print(f"获取到 {len(valid_obs)} 个有效观测值")

# 写入数据库
inserted_count = 0
for obs in valid_obs:
    value = round(float(obs["value"]), 1)
    date_str = obs["date"]  # 格式：YYYY-MM-DD
    updated_at = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    doc = {
        "name": "失业率",
        "value": value,
        "unit": "%",
        "trend": "down" if value < 4.5 else "up" if value > 5.0 else "stable",
        "updated_at": updated_at,
        "source": "FRED UNRATE",
    }

    # 插入数据（按日期去重）
    result = collection.update_one(
        {"name": "失业率", "updated_at": updated_at},
        {"$set": doc},
        upsert=True
    )

    if result.upserted_id or result.modified_count > 0:
        inserted_count += 1
        print(f"  {date_str}: {value:.1f}%")

print(f"\n成功回填 {inserted_count} 条失业率历史数据")
print(f"  时间范围: {valid_obs[0]['date']} 至 {valid_obs[-1]['date']}")
