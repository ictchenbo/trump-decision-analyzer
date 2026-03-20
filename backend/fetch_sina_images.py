#!/usr/bin/env python3
"""
新浪图片搜索采集器 — 采集特朗普和伊朗相关图片。

用法：
  python fetch_sina_images.py                    # 默认采集特朗普+伊朗，各最新 20 张
  python fetch_sina_images.py --limit 50         # 各采集最新 50 张
  python fetch_sina_images.py --keyword 伊朗     # 只采集伊朗
  python fetch_sina_images.py --dry-run          # 只打印，不写库
"""

import sys
import os
import re
import argparse
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from pymongo.errors import DuplicateKeyError
from app.core.database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_sina_images(keyword: str = "特朗普", limit: int = 20) -> List[Dict[str, Any]]:
    """
    从新浪图片搜索采集图片。

    Args:
        keyword: 搜索关键词
        limit: 最多采集数量

    Returns:
        图片列表，每项包含 url, title, source_url, crawled_at
    """
    images = []
    page = 1
    per_page = 10

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    while len(images) < limit:
        encoded_keyword = requests.utils.quote(keyword)
        url = f"https://search.sina.com.cn/img?q={encoded_keyword}&range=all&c=img&num={per_page}&page={page}"
        logger.info(f"正在采集第 {page} 页: {url}")

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
            html = resp.text
        except Exception as e:
            logger.error(f"请求失败: {e}")
            break

        # 计数本页找到数量
        page_start_count = len(images)

        # 解析 HTML
        soup = BeautifulSoup(html, 'html.parser')

        # 查找所有图片容器
        img_items = soup.find_all('div', class_='img-item')
        if not img_items:
            # 尝试另一种结构
            img_items = soup.find_all('div', class_='box')

        if not img_items:
            logger.warning(f"第 {page} 页未找到图片，尝试正则提取")
            # 使用正则提取
            # 提取所有 n.sinaimg.cn 图片
            img_urls = re.findall(r'<img[^>]+src="(https://n\.sinaimg\.cn/[^"]+)"', html)
            # 提取对应的 alt 文本（尽力匹配）
            img_alts = re.findall(r'<img[^>]+alt="([^"]*)"[^>]+src="https://n\.sinaimg\.cn', html)
            matches = list(zip(img_urls, img_alts + [''] * len(img_urls)))
            for img_url, alt_text in matches:
                if len(images) >= limit:
                    break
                images.append({
                    "url": img_url,
                    "title": alt_text or keyword,
                    "source_url": url,
                    "crawled_at": datetime.now(timezone.utc),
                })
                logger.info(f"  [{len(images)}] {img_url[:80]}")
        else:
            for item in img_items:
                if len(images) >= limit:
                    break

                img_tag = item.find('img')
                if not img_tag:
                    continue

                img_url = img_tag.get('src', '')
                if not img_url or not img_url.startswith('http'):
                    continue

                title = img_tag.get('alt', '') or img_tag.get('title', '') or keyword

                images.append({
                    "url": img_url,
                    "title": title,
                    "source_url": url,
                    "crawled_at": datetime.now(timezone.utc),
                })
                logger.info(f"  [{len(images)}] {title[:40]} | {img_url[:60]}")

        if len(images) >= limit:
            break

        # 如果本页没有新图片，停止翻页
        page_found = len(images) - page_start_count if 'page_start_count' in locals() else 0
        if page_found == 0:
            logger.info("没有更多图片，停止采集")
            break

        page += 1

    logger.info(f"共采集 {len(images)} 张图片")
    return images[:limit]


def save_images(images: List[Dict[str, Any]]) -> tuple[int, int]:
    """
    写入数据库，返回 (inserted, skipped)。
    """
    if not images:
        return 0, 0

    db.connect()
    col = db.db["trump_images"]
    now = datetime.utcnow()
    inserted = skipped = 0

    for img in images:
        img.setdefault("created_at", now)
        img.setdefault("updated_at", now)
        try:
            result = col.update_one(
                {"url": img["url"]},
                {"$setOnInsert": img},
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


def main(keyword: str, limit: int, dry_run: bool):
    images = fetch_sina_images(keyword, limit)

    if not images:
        logger.info("没有采集到图片")
        return

    if dry_run:
        logger.info(f"[dry-run] 共 {len(images)} 张，未写入数据库")
    else:
        inserted, skipped = save_images(images)
        logger.info(f"入库完成：新增 {inserted} 张，跳过重复 {skipped} 张")


def main_batch(keywords: list, limit_per: int, dry_run: bool):
    """批量采集多个关键词"""
    total_inserted = 0
    total_skipped = 0
    for keyword in keywords:
        logger.info(f"===== 开始采集关键词: {keyword} =====")
        images = fetch_sina_images(keyword, limit_per)
        if not images:
            logger.warning(f"关键词 '{keyword}' 未采集到图片，跳过")
            continue
        if dry_run:
            logger.info(f"[dry-run] '{keyword}': {len(images)} 张，未写入")
            total_skipped += len(images)
        else:
            inserted, skipped = save_images(images)
            total_inserted += inserted
            total_skipped += skipped
    logger.info(f"===== 批量采集完成 =====")
    if not dry_run:
        logger.info(f"总计：新增 {total_inserted} 张，跳过重复 {total_skipped} 张")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="采集新浪图片搜索结果")
    parser.add_argument("--keyword", type=str,
                        help="搜索关键词，不指定则默认采集 ['特朗普', '伊朗']")
    parser.add_argument("--limit", type=int, default=20,
                        help="最多采集张数，默认 20 每关键词")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印，不写库")
    args = parser.parse_args()

    if args.keyword:
        main(args.keyword, args.limit, args.dry_run)
    else:
        # 默认采集多个关键词：特朗普 + 伊朗
        main_batch(['特朗普', '伊朗'], args.limit, args.dry_run)
