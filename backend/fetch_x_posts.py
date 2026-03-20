#!/usr/bin/env python3
"""
X (Twitter) 采集器 — 基于 twikit 采集指定用户的推文。

认证方式（二选一，优先使用 cookies）：
  方式一（推荐）：浏览器导出 cookies 文件
    1. 浏览器登录 x.com
    2. 安装 "Cookie-Editor" 扩展，导出为 JSON 格式
    3. 保存到 backend/x_cookies.json
  方式二：账号密码（可能被 Cloudflare 拦截）
    在 .env 中配置 X_ACCOUNTS 和 X_PROXY

依赖 .env 配置：
  X_COOKIES_FILE    — cookies 文件路径，默认 x_cookies.json
  X_ACCOUNTS        — 账号，格式：username:password:email（方式二）
  X_TARGET_USERS    — 采集目标用户（逗号分隔，不含@），默认 realDonaldTrump
  X_PROXY           — 代理地址，如 http://127.0.0.1:7890

用法：
  python fetch_x_posts.py                    # 采集最新 20 条
  python fetch_x_posts.py --limit 50         # 采集最新 50 条
  python fetch_x_posts.py --since 2026-02-28 # 采集指定日期以来的全部
  python fetch_x_posts.py --dry-run          # 只打印，不写库
"""

import sys
import os
import json
import argparse
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from pymongo.errors import DuplicateKeyError
from twikit import Client
from app.core.database import db
from app.ingestion.trump_statement_ingestor import analyze_sentiment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# cookies 文件默认路径（相对于本脚本所在目录）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_COOKIES_FILE = os.path.join(_SCRIPT_DIR, "x_cookies.json")


async def init_client() -> Client:
    """
    初始化 twikit Client。
    优先使用 cookies 文件，其次尝试账号密码登录。
    """
    proxy = os.environ.get("X_PROXY", "").strip() or None
    client = Client("en-US", proxy=proxy)

    cookies_file = os.environ.get("X_COOKIES_FILE", _DEFAULT_COOKIES_FILE)

    # ── 方式一：cookies 文件 ──────────────────────────────────────
    if os.path.exists(cookies_file):
        logger.info(f"使用 cookies 文件登录：{cookies_file}")
        with open(cookies_file, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # 支持两种 cookies 格式：
        #   1. Cookie-Editor 导出的列表格式：[{"name": ..., "value": ...}, ...]
        #   2. 字典格式：{"auth_token": ..., "ct0": ...}
        if isinstance(raw, list):
            cookies = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
        else:
            cookies = raw

        client.set_cookies(cookies)
        logger.info("cookies 加载完成")
        return client

    # ── 方式二：账号密码 ──────────────────────────────────────────
    accounts_str = os.environ.get("X_ACCOUNTS", "").strip()
    if not accounts_str:
        raise RuntimeError(
            "未找到认证信息。请选择以下任一方式：\n"
            "  方式一（推荐）：在浏览器登录 x.com，用 Cookie-Editor 扩展导出 cookies，\n"
            f"                  保存到 {cookies_file}\n"
            "  方式二：在 .env 中配置 X_ACCOUNTS=username:password:email"
        )

    parts = accounts_str.split(",")[0].strip().split(":")
    username = parts[0]
    password = parts[1]
    email    = parts[2] if len(parts) > 2 else ""

    logger.info(f"使用账号密码登录：@{username}")
    await client.login(auth_info_1=username, auth_info_2=email, password=password)

    # 登录成功后保存 cookies，下次直接复用
    client.save_cookies(cookies_file)
    logger.info(f"cookies 已保存到 {cookies_file}")

    return client


async def fetch_user_tweets(
    client: Client,
    username: str,
    limit: int = 20,
    since_date: datetime = None,
) -> List[Dict[str, Any]]:
    """采集指定用户的推文。"""
    logger.info(f"查询 @{username} 的用户信息...")
    user = await client.get_user_by_screen_name(username)
    logger.info(f"@{username} id={user.id}，开始采集推文...")

    posts = []
    cursor = None

    while True:
        if cursor:
            batch = await client.get_user_tweets(user.id, "Tweets", count=20, cursor=cursor)
        else:
            batch = await client.get_user_tweets(user.id, "Tweets", count=20)

        if not batch:
            break

        stop = False
        for tweet in batch:
            # 解析发帖时间
            try:
                post_time = datetime.strptime(
                    tweet.created_at, "%a %b %d %H:%M:%S %z %Y"
                )
            except (ValueError, AttributeError):
                post_time = datetime.now(timezone.utc)

            # 如果指定了 since_date，遇到更早的帖子就停止
            if since_date and post_time < since_date:
                stop = True
                break

            content = tweet.text or tweet.full_text or ""
            if not content:
                continue

            sentiment, score = analyze_sentiment(content)
            posts.append({
                "content":         content,
                "source":          "X (Twitter)",
                "post_time":       post_time,
                "likes":           getattr(tweet, "favorite_count", 0) or 0,
                "shares":          getattr(tweet, "retweet_count", 0) or 0,
                "url":             f"https://x.com/{username}/status/{tweet.id}",
                "post_id":         str(tweet.id),
                "sentiment":       sentiment,
                "sentiment_score": score,
            })
            logger.info(f"  [{post_time.strftime('%m-%d %H:%M')}] {content[:70]}")

            if not since_date and len(posts) >= limit:
                stop = True
                break

        if stop:
            break

        # 翻页
        cursor = getattr(batch, "next_cursor", None)
        if not cursor:
            break

    logger.info(f"共采集 {len(posts)} 条推文")
    return posts


def save_posts(posts: List[Dict[str, Any]]) -> tuple[int, int]:
    """写入数据库，返回 (inserted, skipped)。"""
    if not posts:
        return 0, 0

    db.connect()
    col = db.db["trump_statements"]
    now = datetime.utcnow()
    inserted = skipped = 0

    for p in posts:
        p.setdefault("created_at", now)
        p.setdefault("updated_at", now)
        try:
            result = col.update_one(
                {"post_id": p["post_id"]},
                {"$setOnInsert": p},
                upsert=True,
            )
            if result.upserted_id:
                inserted += 1
            else:
                skipped += 1
        except DuplicateKeyError:
            skipped += 1

    db.disconnect()
    return inserted, skipped


async def main(username: str, limit: int, since_date: datetime, dry_run: bool):
    client = await init_client()
    posts = await fetch_user_tweets(client, username, limit, since_date)

    if not posts:
        logger.info("没有新推文")
        return

    if dry_run:
        logger.info(f"[dry-run] 共 {len(posts)} 条，未写入数据库")
    else:
        inserted, skipped = save_posts(posts)
        logger.info(f"入库完成：新增 {inserted} 条，跳过重复 {skipped} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="采集 X (Twitter) 指定用户的推文")
    parser.add_argument("--user",    type=str, default=None,
                        help="X 用户名（不含@），默认从 X_TARGET_USERS 读取")
    parser.add_argument("--limit",   type=int, default=20,
                        help="最多采集条数，默认 20（--since 存在时忽略）")
    parser.add_argument("--since",   type=str, default=None,
                        help="起始日期 YYYY-MM-DD，采集此日期以来的全部推文")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印，不写库")
    args = parser.parse_args()

    target_user = args.user or os.environ.get("X_TARGET_USERS", "realDonaldTrump").split(",")[0].strip()
    since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None

    asyncio.run(main(target_user, args.limit, since_dt, args.dry_run))
