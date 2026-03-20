#!/usr/bin/env python3
"""
补采 @realDonaldTrump 从指定日期以来的全部 Truth Social 帖子。

用法：
  python backfill_truth_social.py                    # 默认从 2026-02-28 开始
  python backfill_truth_social.py --since 2026-02-01 # 自定义起始日期
  python backfill_truth_social.py --dry-run          # 只打印，不写库
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

from pymongo.errors import DuplicateKeyError
from app.core.database import db
from app.ingestion.trump_statement_ingestor import TrumpStatementIngestor, analyze_sentiment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def run(since_date: datetime, dry_run: bool = False):
    ingestor = TrumpStatementIngestor()
    api = ingestor._get_truthbrush_api()

    logger.info(f"开始采集 @{ingestor.TRUTH_SOCIAL_USERNAME} 自 {since_date.date()} 以来的全部帖子...")

    posts = []
    for item in api.pull_statuses(
        username=ingestor.TRUTH_SOCIAL_USERNAME,
        replies=False,
        created_after=since_date,
    ):
        raw = item.get("content", "")
        content = re.sub(r"<[^>]+>", "", raw).strip()
        if not content:
            continue

        created_at_raw = item.get("created_at", "")
        try:
            post_time = datetime.fromisoformat(
                created_at_raw.replace("Z", "+00:00")
            ).replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            post_time = datetime.now(timezone.utc)

        post_id = str(item.get("id", ""))
        url = item.get("url") or f"https://truthsocial.com/@{ingestor.TRUTH_SOCIAL_USERNAME}/{post_id}"

        sentiment, score = analyze_sentiment(content)
        posts.append({
            "content":         content,
            "source":          "Truth Social",
            "post_time":       post_time,
            "likes":           item.get("favourites_count", 0),
            "shares":          item.get("reblogs_count", 0),
            "url":             url,
            "post_id":         post_id,
            "sentiment":       sentiment,
            "sentiment_score": score,
        })
        logger.info(f"  [{post_time.strftime('%m-%d %H:%M')}] id={post_id}  {content[:70]}")

    logger.info(f"共采集 {len(posts)} 条帖子")

    if dry_run or not posts:
        logger.info("[dry-run] 未写入数据库" if dry_run else "没有新帖子")
        return

    db.connect()
    col = db.db["trump_statements"]
    now = datetime.utcnow()
    inserted = skipped = 0

    for s in posts:
        s.setdefault("created_at", now)
        s.setdefault("updated_at", now)
        try:
            result = col.update_one(
                {"post_id": s["post_id"]},
                {"$setOnInsert": s},
                upsert=True,
            )
            if result.upserted_id:
                inserted += 1
            else:
                skipped += 1
        except DuplicateKeyError:
            skipped += 1

    db.disconnect()
    logger.info(f"入库完成：新增 {inserted} 条，跳过重复 {skipped} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="补采 Truth Social 历史帖子")
    parser.add_argument("--since", type=str, default="2026-02-28",
                        help="起始日期 YYYY-MM-DD，默认 2026-02-28")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = parser.parse_args()

    since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    run(since_date=since_dt, dry_run=args.dry_run)
