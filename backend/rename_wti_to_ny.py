#!/usr/bin/env python3
"""
将数据库中所有 "WTI原油" 改名为 "纽约原油"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()
from app.core.database import db

db.connect()

# 1. 更新 real_time_data 集合
rt_col = db.db["real_time_data"]
result = rt_col.update_many(
    {"name": "WTI原油"},
    {"$set": {"name": "纽约原油"}}
)
print(f"real_time_data: 更新 {result.modified_count} 条")

# 2. 更新 factor_scores 集合中的 raw_indicators
# 需要遍历每个文档，如果有 WTI原油 键，重命名为 纽约原油
fs_col = db.db["factor_scores"]
cursor = fs_col.find({"raw_indicators.WTI原油": {"$exists": True}})
updated = 0
for doc in cursor:
    raw = doc["raw_indicators"]
    if "WTI原油" in raw:
        raw["纽约原油"] = raw.pop("WTI原油")
        if "WTI原油收益率" in raw:
            raw["纽约原油收益率"] = raw.pop("WTI原油收益率")
        fs_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"raw_indicators": raw}}
        )
        updated += 1
print(f"factor_scores: 更新 {updated} 个文档")

print("\nDone!")
db.disconnect()
