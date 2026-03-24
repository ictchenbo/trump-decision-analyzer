#!/usr/bin/env python3
"""
检查 real_time_data 表中各指标的时间范围
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone
from app.core.database import db

def main():
    if not db.client:
        db.connect()
    
    collection = db.db["real_time_data"]
    
    # 获取所有指标
    indicators = collection.distinct("name")
    print(f"找到 {len(indicators)} 个指标:\n")
    
    results = []
    for indicator in indicators:
        # 获取最早记录
        first = collection.find_one({"name": indicator}, sort=[("updated_at", 1)])
        # 获取最新记录
        last = collection.find_one({"name": indicator}, sort=[("updated_at", -1)])
        # 获取记录数量
        count = collection.count_documents({"name": indicator})
        
        first_time = first["updated_at"] if first else None
        last_time = last["updated_at"] if last else None
        
        results.append({
            "name": indicator,
            "count": count,
            "first": first_time,
            "last": last_time
        })
        print(f"{indicator}:")
        print(f"  记录数: {count}")
        print(f"  最早: {first_time}")
        print(f"  最晚: {last_time}")
        print()
    
    # 检查哪些指标需要回填（需要覆盖到2026-02-28）
    target_date = datetime(2026, 2, 28, tzinfo=timezone.utc)
    print("\n" + "="*60)
    print("需要回填的指标（最早时间晚于 2026-02-28）:")
    print("="*60)
    need_backfill = []
    for r in results:
        if r["first"] is None or r["first"] > target_date:
            need_backfill.append(r)
            print(f"{r['name']}: 最早 {r['first']}")
    
    print(f"\n共 {len(need_backfill)} 个指标需要回填")

if __name__ == "__main__":
    main()
