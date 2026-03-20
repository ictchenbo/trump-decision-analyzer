#!/usr/bin/env python3
"""
非农就业历史数据回填脚本

从 FRED API 获取最近 24 个月的 PAYEMS 数据，计算月度新增值，
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

# 从 FRED 获取最近 24 个月的 PAYEMS 数据
print("正在从 FRED API 获取 PAYEMS 历史数据...")
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "PAYEMS",
    "api_key": FRED_API_KEY,
    "file_type": "json",
    "sort_order": "desc",
    "limit": 25,  # 取 25 个月，计算 24 个月度新增
}

resp = requests.get(url, params=params, timeout=15)
resp.raise_for_status()
observations = resp.json()["observations"]

# 过滤掉无效值，按时间正序排列
valid_obs = [o for o in observations if o["value"] != "."]
valid_obs.reverse()  # 从旧到新排序

if len(valid_obs) < 2:
    print("错误：FRED 数据不足，无法计算月度新增")
    sys.exit(1)

print(f"获取到 {len(valid_obs)} 个有效观测值")

# 计算月度新增并写入数据库
inserted_count = 0
for i in range(1, len(valid_obs)):
    prev_val = float(valid_obs[i-1]["value"])
    curr_val = float(valid_obs[i]["value"])
    change = round(curr_val - prev_val, 1)

    # 使用当前月的日期作为 updated_at
    date_str = valid_obs[i]["date"]  # 格式：YYYY-MM-DD
    updated_at = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    doc = {
        "name": "非农就业",
        "value": change,
        "unit": "千人",
        "trend": "up" if change > 0 else "down" if change < 0 else "stable",
        "updated_at": updated_at,
        "source": "FRED PAYEMS (月度新增)",
    }

    # 插入数据（按日期去重）
    result = collection.update_one(
        {"name": "非农就业", "updated_at": updated_at},
        {"$set": doc},
        upsert=True
    )

    if result.upserted_id or result.modified_count > 0:
        inserted_count += 1
        print(f"  {date_str}: {change:+.1f} 千人")

print(f"\n成功回填 {inserted_count} 条非农就业历史数据")
print(f"  时间范围: {valid_obs[1]['date']} 至 {valid_obs[-1]['date']}")
