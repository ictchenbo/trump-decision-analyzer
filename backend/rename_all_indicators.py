#!/usr/bin/env python3
"""
批量重命名数据库中的指标名称
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()
from app.core.database import db

db.connect()

# 名称映射：旧名称 -> 新名称
NAME_MAP = {
    '纳斯达克': '纳斯达克指数',
    '道琼斯': '道琼斯指数',
    'VIX指数': '波动率指数VIX',
    '布伦特原油': '布伦特原油期货',
    'WTI原油': '纽约原油',
    '纽约原油': '纽约原油期货',
    '黄金价格': '纽约黄金',
    '美国汽油价格': 'RBOB汽油价格',
    '地缘风险溢价': '布油-WTI地缘溢价',
    '美国10年期国债': '10年期国债收益率',
    '美国2年期国债': '2年期国债收益率',
}

# 1. 更新 real_time_data 集合
rt_col = db.db["real_time_data"]
total_updated_rt = 0
for old_name, new_name in NAME_MAP.items():
    result = rt_col.update_many(
        {"name": old_name},
        {"$set": {"name": new_name}}
    )
    print(f"real_time_data [{old_name}] -> [{new_name}]: 更新 {result.modified_count} 条")
    total_updated_rt += result.modified_count

# 2. 更新 factor_scores 集合中的 raw_indicators 字典键
fs_col = db.db["factor_scores"]
total_updated_fs = 0
cursor = fs_col.find({})
for doc in cursor:
    raw = doc.get("raw_indicators", {})
    if not isinstance(raw, dict):
        continue
    changed = False
    for old_name, new_name in NAME_MAP.items():
        if old_name in raw:
            raw[new_name] = raw.pop(old_name)
            changed = True
    if changed:
        fs_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"raw_indicators": raw}}
        )
        total_updated_fs += 1

print(f"\n=== 完成 ===")
print(f"real_time_data 总共更新: {total_updated_rt} 条")
print(f"factor_scores 总共更新: {total_updated_fs} 个文档")

db.disconnect()
