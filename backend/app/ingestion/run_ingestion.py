#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime, timezone
import logging
from typing import List
from dotenv import load_dotenv
from app.core.database import db
from app.ingestion.real_time_ingestor import ALL_INGESTORS
from app.ingestion.trump_statement_ingestor import TRUMP_STATEMENT_INGESTOR
from app.ingestion.factor_score_ingestor import run_factor_score_ingestor
from app.ingestion.war_peace_ingestor import run_war_peace_ingestor
from app.ingestion.base_ingestor import BaseDataIngestor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ingestion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# ── 采集器分层配置 ──────────────────────────────────────────────
# 根据数据更新频率将采集器分为三层，避免无效采集

# 高频：市场类数据，交易时段30秒，非交易时段5分钟
HIGH_FREQ_SOURCES = {
    'sp500', 'nasdaq', 'dow_jones', 'vix', 'brent_oil', 'wti_oil',
    'us_treasury_10y', 'geopolitical_risk_premium', 'dollar_index', 'gasoline'
}

# 中频：Polymarket 预测市场，5-10分钟
MID_FREQ_SOURCES = {
    'polymarket_trump_political_risk', 'polymarket_military_strike'
}

# 低频：民调、BLS月度数据，每小时或每天
LOW_FREQ_SOURCES = {
    'trump_approval', 'nonfarm_payroll', 'unemployment_rate', 'cpi_yoy'
}

def is_us_market_hours() -> bool:
    """判断当前是否为美股交易时段（美东9:30-16:00，周一至周五）"""
    now_utc = datetime.now(timezone.utc)
    # 美东时间 = UTC-5 (EST) 或 UTC-4 (EDT)，这里简化为 UTC-5
    us_hour = (now_utc.hour - 5) % 24
    us_weekday = now_utc.weekday()  # 0=周一, 6=周日

    # 周一至周五，9:30-16:00（简化为10-16点）
    return us_weekday < 5 and 10 <= us_hour < 16

def ensure_db():
    if not db.client:
        logger.info("重新连接数据库...")
        db.connect()

def save_real_time_data(data_list: List[dict]):
    """
    存储实时指标数据。
    对市场类指标（股票/能源），若最新一条值与当前值相同则跳过，避免写入非交易时间的重复收盘价。
    """
    MARKET_NAMES = {'标普500', '纳斯达克指数', '道琼斯指数', '波动率指数VIX', '布伦特原油期货', '纽约原油期货', '美元指数', 'RBOB汽油价格', '10年期国债收益率', '布油-WTI地缘溢价'}
    try:
        collection = db.db["real_time_data"]
        inserted = 0
        skipped = 0
        for data in data_list:
            name = data.get("name")
            if name in MARKET_NAMES:
                last = collection.find_one({"name": name}, sort=[("updated_at", -1)])
                if last and last.get("value") == data.get("value"):
                    skipped += 1
                    continue
            collection.insert_one(data)
            inserted += 1
        logger.info(f"实时数据入库: 新增 {inserted} 条，跳过重复 {skipped} 条")
    except Exception as e:
        logger.error(f"实时数据入库失败: {e}")

def save_statements(statements: List[dict]):
    if not statements:
        return
    from pymongo.errors import DuplicateKeyError
    collection = db.db["trump_statements"]
    now = datetime.utcnow()
    inserted = 0
    skipped = 0
    for s in statements:
        # post_time 统一转为 datetime 对象存入 MongoDB
        raw_time = s.get("post_time")
        if isinstance(raw_time, str):
            try:
                s["post_time"] = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError:
                s["post_time"] = now
        elif not isinstance(raw_time, datetime):
            s["post_time"] = now

        s.setdefault("created_at", now)
        s.setdefault("updated_at", now)

        try:
            # 按 post_id 去重（Truth Social），无 post_id 则按 content+source 去重
            if s.get("post_id"):
                result = collection.update_one(
                    {"post_id": s["post_id"]},
                    {"$setOnInsert": s},
                    upsert=True
                )
            else:
                result = collection.update_one(
                    {"content": s["content"], "source": s["source"]},
                    {"$setOnInsert": s},
                    upsert=True
                )
            if result.upserted_id:
                inserted += 1
            else:
                skipped += 1
        except DuplicateKeyError:
            skipped += 1

    logger.info(f"言论数据入库完成: 新增 {inserted} 条，跳过重复 {skipped} 条")

def run_real_time_ingestors(cycle_count: int = 0):
    """
    分层采集实时指标。
    cycle_count: 当前采集周期计数（每30秒+1）
    """
    all_data = []
    is_market_open = is_us_market_hours()

    for ingestor in ALL_INGESTORS:
        source = ingestor.source_name

        # 高频数据：交易时段每次采集，非交易时段每10个周期（5分钟）采集一次
        if source in HIGH_FREQ_SOURCES:
            if not is_market_open and cycle_count % 10 != 0:
                continue

        # 中频数据：每10个周期（5分钟）采集一次
        elif source in MID_FREQ_SOURCES:
            if cycle_count % 10 != 0:
                continue

        # 低频数据：每120个周期（1小时）采集一次
        elif source in LOW_FREQ_SOURCES:
            if cycle_count % 120 != 0:
                continue

        logger.info(f"采集 {source}...")
        result = ingestor.run()
        if result["success"]:
            all_data.append(result["data"])
        else:
            logger.error(f"采集失败: {result['error']}")

    if all_data:
        save_real_time_data(all_data)

def run_statement_ingestor(cycle_count: int = 0):
    """
    采集特朗普言论（Truth Social + 新闻）。
    每10个周期（5分钟）采集一次，及时捕获新言论。
    """
    if cycle_count % 10 != 0:
        return

    logger.info("采集特朗普言论...")
    result = TRUMP_STATEMENT_INGESTOR.run()
    if result["success"]:
        statements = result["data"].get("statements", [])

        # ── 修正顺序：先去重筛选出新数据，再做 LLM  enrichment ──
        # 先过滤出数据库中不存在的数据，避免对重复数据调用大模型浪费 token
        from app.ingestion.llm_enricher import enrich_statements_batch
        collection = db.db["trump_statements"]

        # 筛选出确实需要插入的新数据
        new_statements = []
        skipped_existing = 0
        for s in statements:
            if s.get("post_id"):
                exists = collection.find_one({"post_id": s["post_id"]}, {"_id": 1})
            else:
                exists = collection.find_one({"content": s["content"], "source": s["source"]}, {"_id": 1})
            if exists:
                skipped_existing += 1
            else:
                new_statements.append(s)

        if skipped_existing:
            logger.info(f"已跳过 {skipped_existing} 条已存在言论，仅对 {len(new_statements)} 条新数据进行处理")

        # 只对新数据做 LLM 增强
        if new_statements:
            enrich_statements_batch(new_statements)

        # 保存所有数据（去重逻辑会再次检查，但此时新数据已经完成 enrichment）
        save_statements(statements)
    else:
        logger.error(f"言论采集失败: {result['error']}")


def run_x_ingestor(cycle_count: int = 0):
    """
    采集 X (Twitter) 指定用户推文。
    每20个周期（10分钟）采集一次。
    cookies 文件或 X_ACCOUNTS 均未配置时静默跳过。
    """
    if cycle_count % 20 != 0:
        return

    import asyncio
    from fetch_x_posts import init_client, fetch_user_tweets, _DEFAULT_COOKIES_FILE

    has_cookies = os.path.exists(_DEFAULT_COOKIES_FILE)
    has_accounts = bool(os.environ.get("X_ACCOUNTS", "").strip())
    if not has_cookies and not has_accounts:
        return

    target_users = os.environ.get("X_TARGET_USERS", "realDonaldTrump").strip()
    for username in target_users.split(","):
        username = username.strip()
        if not username:
            continue
        logger.info(f"采集 X @{username} 推文...")
        try:
            async def _fetch(u=username):
                client = await init_client()
                return await fetch_user_tweets(client, u, limit=20)
            posts = asyncio.run(_fetch())
            save_statements(posts)
        except Exception as e:
            logger.error(f"X 采集失败 @{username}: {e}")

def run_all_ingestors(cycle_count: int = 0):
    """
    执行全量数据采集。
    cycle_count: 当前采集周期计数，用于控制不同频率的采集器
    """
    logger.info(f"=== 开始执行数据采集 (周期 {cycle_count}) ===")
    try:
        ensure_db()
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return

    run_real_time_ingestors(cycle_count)
    run_statement_ingestor(cycle_count)
    # 暂时不需要采集X
    # run_x_ingestor(cycle_count)

    # 实时指标采集完成后计算因子得分（每次都计算，因为高频数据可能已更新）
    try:
        result = run_factor_score_ingestor()
        if result:
            logger.info(f"因子得分计算完成: 综合指数={result['composite_index']}")
    except Exception as e:
        logger.error(f"因子得分计算失败: {e}")

    # 计算战争与和平指数
    try:
        result = run_war_peace_ingestor()
        if result:
            logger.info(f"战争与和平指数计算完成: 综合指数={result['composite_index']}")
    except Exception as e:
        logger.error(f"战争与和平指数计算失败: {e}")

    logger.info("=== 本次采集完成 ===")

def schedule_jobs(interval_seconds: int = 30):
    """
    定时采集任务调度器。
    使用周期计数器实现分层采集：
    - 高频数据（市场类）：交易时段每30秒，非交易时段每5分钟
    - 中频数据（Polymarket）：每5分钟
    - 低频数据（民调/BLS）：每1小时
    - 言论数据：每5分钟
    """
    logger.info(f"=== 定时采集任务已启动，基础间隔 {interval_seconds} 秒 ===")
    logger.info("采集策略：")
    logger.info("  - 高频（市场类）：交易时段30秒，非交易时段5分钟")
    logger.info("  - 中频（Polymarket）：5分钟")
    logger.info("  - 低频（民调/BLS）：1小时")
    logger.info("  - 言论：5分钟")

    cycle_count = 0
    while True:
        try:
            start_time = time.time()
            run_all_ingestors(cycle_count)
            cycle_count += 1

            # 防止计数器溢出，每天重置（2880个周期 = 24小时）
            if cycle_count >= 2880:
                cycle_count = 0

            elapsed = time.time() - start_time
            time.sleep(max(0, interval_seconds - elapsed))
        except KeyboardInterrupt:
            logger.info("=== 采集任务已停止 ===")
            break
        except Exception as e:
            logger.error(f"任务运行异常: {e}")
            time.sleep(5)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="特朗普决策影响因子分析系统数据采集程序")
    parser.add_argument("--interval", type=int, default=30, help="基础采集间隔秒数，默认30秒")
    parser.add_argument("--once", action="store_true", help="仅运行一次采集任务（全量采集所有指标）")
    args = parser.parse_args()

    if args.once:
        # 单次运行模式：cycle_count=0 会触发所有采集器（包括低频）
        run_all_ingestors(cycle_count=0)
        logger.info("=== 单次采集任务完成 ===")
    else:
        schedule_jobs(args.interval)

