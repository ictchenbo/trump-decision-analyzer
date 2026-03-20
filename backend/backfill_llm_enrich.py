#!/usr/bin/env python3
"""
对数据库中已有的 trump_statements 进行 LLM 补全（翻译 + 鹰派评分）。

用法：
  python backfill_llm_enrich.py            # 补全所有未处理条目
  python backfill_llm_enrich.py --limit 50 # 只处理前 50 条
  python backfill_llm_enrich.py --force    # 强制重新处理所有条目（含已有结果的）

依赖 .env 中的 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_ENABLED。
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import db
from app.ingestion.llm_enricher import enrich_statement, _is_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def run(limit: int = 0, force: bool = False):
    if not _is_enabled():
        logger.error("LLM_ENABLED=false，请先在 .env 中启用 LLM 后再运行此脚本")
        sys.exit(1)

    db.connect()
    col = db.db["trump_statements"]

    # 查询条件：force=True 时处理全部，否则只处理 llm_enriched 不为 True 的
    # 注意：$ne True 不匹配 None/缺失字段，需用 $in 覆盖 null/false/缺失三种情况
    query = {} if force else {"llm_enriched": {"$in": [None, False]}}
    total_pending = col.count_documents(query)
    to_process = min(total_pending, limit) if limit > 0 else total_pending
    logger.info(f"待处理: {total_pending} 条，本次处理: {to_process} 条")

    if to_process == 0:
        logger.info("没有需要处理的条目，退出")
        return

    cursor = col.find(query, {"_id": 1, "content": 1}).limit(to_process)

    ok = fail = skip = 0
    for doc in cursor:
        doc_id = doc["_id"]
        content = (doc.get("content") or "").strip()
        if not content:
            skip += 1
            continue

        result = enrich_statement(content)

        if result["llm_enriched"]:
            col.update_one(
                {"_id": doc_id},
                {"$set": {
                    "translation":   result["translation"],
                    "hawkish_score": result["hawkish_score"],
                    "llm_enriched":  True,
                }}
            )
            ok += 1
            logger.info(f"[{ok+fail}/{to_process}] OK  score={result['hawkish_score']:>3}  {content[:60]}")
        else:
            fail += 1
            logger.warning(f"[{ok+fail}/{to_process}] FAIL  {content[:60]}")

    logger.info(f"完成：成功 {ok}，失败 {fail}，跳过空内容 {skip}")
    db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 补全数据库存量言论数据")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数，0=全部")
    parser.add_argument("--force", action="store_true", help="强制重新处理已有结果的条目")
    args = parser.parse_args()
    run(limit=args.limit, force=args.force)
