#!/usr/bin/env python3
"""
从 Truth Social 采集 @realDonaldTrump 最新帖子并存入数据库。

用法：
  python fetch_truth_social.py              # 采集最新 20 条
  python fetch_truth_social.py --limit 50   # 采集最新 50 条
  python fetch_truth_social.py --since-id 116207137060584916  # 增量采集
  python fetch_truth_social.py --dry-run    # 只打印，不写库

依赖 .env 中的：
  TRUTHSOCIAL_USERNAME + TRUTHSOCIAL_PASSWORD  （账号密码方式）
  或 TRUTHSOCIAL_TOKEN                          （token 方式）
"""

import sys
import os
import argparse
import logging
import re
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import db
from app.ingestion.trump_statement_ingestor import TrumpStatementIngestor, analyze_sentiment, count_hawkish_words, analyze_hawkish_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def save_statements(statements: list, dry_run: bool = False) -> tuple[int, int]:
    """写入数据库，返回 (inserted, skipped)。"""
    if dry_run:
        return len(statements), 0

    col = db.db["trump_statements"]
    now = datetime.utcnow()
    inserted = skipped = 0

    for s in statements:
        s.setdefault("created_at", now)
        s.setdefault("updated_at", now)

        if s.get("post_id"):
            result = col.update_one(
                {"post_id": s["post_id"]},
                {"$setOnInsert": s},
                upsert=True,
            )
            if result.upserted_id:
                inserted += 1
            else:
                skipped += 1
        else:
            result = col.update_one(
                {"content": s["content"], "source": s["source"]},
                {"$setOnInsert": s},
                upsert=True,
            )
            if result.upserted_id:
                inserted += 1
            else:
                skipped += 1

    return inserted, skipped


def run(limit: int = 20, since_id: str = None, dry_run: bool = False):
    from app.ingestion.llm_enricher import enrich_statements_batch
    ingestor = TrumpStatementIngestor()

    logger.info(f"开始采集 @{ingestor.TRUTH_SOCIAL_USERNAME} 最新帖子（limit={limit}）...")
    try:
        posts = ingestor.fetch_from_truth_social(max_posts=limit, since_id=since_id)
    except Exception as e:
        logger.error(f"采集失败: {e}")
        sys.exit(1)

    if not posts:
        logger.info("没有新帖子")
        return

    logger.info(f"采集到 {len(posts)} 条帖子，开始规则法预处理...")

    for p in posts:
        sentiment, score = analyze_sentiment(p["content"])
        p["sentiment"] = sentiment
        p["sentiment_score"] = score
        # 规则法鹰派词汇计数和评分（保底）
        p["hawkish_word_count"] = count_hawkish_words(p["content"])
        p["hawkish_score"] = analyze_hawkish_score(p["content"])

    # 打印预览
    for p in posts:
        ts = p["post_time"].strftime("%Y-%m-%d %H:%M") if isinstance(p["post_time"], datetime) else p["post_time"]
        print(f"\n[{ts}] id={p['post_id']}  sentiment={p['sentiment']}({p['sentiment_score']:+.2f})")
        print(f"  {p['content'][:120]}")

    if dry_run:
        logger.info(f"[dry-run] 共 {len(posts)} 条，未写入数据库")
        return

    db.connect()

    # ── 修正顺序：先去重筛选出新数据，再做 LLM enrichment ──
    collection = db.db["trump_statements"]
    new_posts = []
    skipped_existing = 0
    for p in posts:
        if p.get("post_id"):
            exists = collection.find_one({"post_id": p["post_id"]}, {"_id": 1})
        else:
            exists = collection.find_one({"content": p["content"], "source": p["source"]}, {"_id": 1})
        if exists:
            skipped_existing += 1
        else:
            new_posts.append(p)

    if skipped_existing:
        logger.info(f"已跳过 {skipped_existing} 条已存在帖子")
    if new_posts:
        logger.info(f"对 {len(new_posts)} 条新帖子进行 LLM 增强...")
        enrich_statements_batch(new_posts)

    inserted, skipped = save_statements(posts, dry_run=False)
    db.disconnect()
    logger.info(f"入库完成：新增 {inserted} 条，跳过重复 {skipped} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="采集 Truth Social @realDonaldTrump 最新帖子")
    parser.add_argument("--limit",    type=int, default=20,  help="最多采集条数，默认 20")
    parser.add_argument("--since-id", type=str, default=None, help="只采集比此 ID 更新的帖子")
    parser.add_argument("--dry-run",  action="store_true",   help="只打印，不写入数据库")
    args = parser.parse_args()

    run(limit=args.limit, since_id=args.since_id, dry_run=args.dry_run)
