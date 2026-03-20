"""
特朗普言行数据采集器 — 使用真实数据源，不生成随机内容。

数据源：
  - Truth Social：truthbrush 库（stanfordio/truthbrush）
    需要 .env 中配置以下任一方式：
      方式一（账号密码）：TRUTHSOCIAL_USERNAME + TRUTHSOCIAL_PASSWORD
      方式二（Token）：TRUTHSOCIAL_TOKEN
  - 新闻媒体：NewsAPI (newsapi.org)
    需要 NEWS_API_KEY 环境变量
"""

import os
import re
import requests
import itertools
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

from .base_ingestor import BaseDataIngestor
from .llm_enricher import enrich_statements_batch


# ── 情感分析规则引擎 ──────────────────────────────────────────
# 从特朗普视角出发：他认为"好"的事情 → 正面，他认为"坏"的事情 → 负面
# 每条规则：(关键词列表, 权重)，权重正负决定方向，绝对值决定强度

POSITIVE_RULES: List[Tuple[List[str], float]] = [
    # 胜利/成就
    (["再次强大", "make america great", "maga", "我们赢了", "伟大的胜利", "历史性", "最好的", "完美的", "太棒了", "非常成功"], 0.8),
    # 经济利好
    (["降息", "减税", "经济增长", "就业增加", "股市上涨", "能源独立", "贸易顺差", "制造业回归"], 0.6),
    # 边境/移民（特朗普视角：管控边境是正面的）
    (["边境安全", "边境是安全的", "阻止非法移民", "驱逐", "修建边墙", "移民管控"], 0.6),
    # 支持者/集会
    (["集会", "支持者", "现场太棒", "人山人海", "创纪录", "民调领先"], 0.5),
    # 对手失败
    (["拜登失败", "民主党失败", "假新闻被揭穿", "深层政府", "他们输了"], 0.5),
]

NEGATIVE_RULES: List[Tuple[List[str], float]] = [
    # 灾难/失败
    (["灾难", "彻底失败", "耻辱", "最糟糕", "一团糟", "崩溃", "危机"], -0.8),
    # 被操纵/不公平
    (["被操纵", "骗局", "舞弊", "不公平", "偷走", "腐败", "勾结"], -0.7),
    # 经济负面
    (["通货膨胀", "油价太高", "失业", "衰退", "债务", "破产", "股市暴跌"], -0.6),
    # 外交失败（特朗普视角）
    (["撤退", "投降", "软弱", "被欺负", "盟友背叛", "阿富汗撤退"], -0.7),
    # 对手攻击我方
    (["起诉", "逮捕", "弹劾", "政治迫害", "猎巫行动"], -0.6),
    # 威胁
    (["战争威胁", "核威胁", "恐怖袭击", "入侵"], -0.5),
]

# 强度修饰词：出现时将基础分乘以系数
INTENSIFIERS = {
    "彻底": 1.4, "完全": 1.3, "非常": 1.2, "极其": 1.4,
    "最": 1.3, "绝对": 1.3, "历史上最": 1.5,
    "有点": 0.6, "可能": 0.7, "也许": 0.7,
}


# 鹰派词汇表（英文+中文）
HAWKWORDS = [
    # 英文
    "attack", "strike", "destroy", "sanction", "military", "threat",
    "war", "bomb", "conflict", "invasion", "kill", "beat", "crush",
    # 中文
    "攻击", "打击", "摧毁", "制裁", "军事", "威胁",
    "战争", "轰炸", "冲突", "入侵", "消灭", "打败", "碾压",
]


def count_hawkish_words(text: str) -> int:
    """
    计算文本中鹰派词汇数量。
    """
    count = 0
    text_lower = text.lower()
    for word in HAWKWORDS:
        if word in text_lower:
            count += 1
    return count


def analyze_sentiment(text: str) -> Tuple[str, float]:
    """
    基于规则的情感分析，从特朗普政治视角出发。
    返回 (sentiment, score)，score 范围 [-1, 1]
    """
    score = 0.0
    text_lower = text.lower()

    for keywords, weight in POSITIVE_RULES:
        for kw in keywords:
            if kw in text_lower or kw in text:
                score += weight
                break

    for keywords, weight in NEGATIVE_RULES:
        for kw in keywords:
            if kw in text_lower or kw in text:
                score += weight  # weight 已经是负数
                break

    intensifier = 1.0
    for word, factor in INTENSIFIERS.items():
        if word in text:
            intensifier = max(intensifier, factor)
    if score != 0:
        score *= intensifier

    score = max(-1.0, min(1.0, score))
    score = round(score, 2)

    if score > 0.2:
        sentiment = "positive"
    elif score < -0.2:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return sentiment, score


# ─────────────────────────────────────────────────────────────

class TrumpStatementIngestor(BaseDataIngestor):
    """
    特朗普言行数据采集器。
    Truth Social 通过 truthbrush 库直接抓取，新闻通过 NewsAPI 获取。
    """

    # 采集目标账号
    TRUTH_SOCIAL_USERNAME = "realDonaldTrump"

    def __init__(self):
        super().__init__("trump_statements")
        self.news_api_key = os.environ.get("NEWS_API_KEY", "")

    def _get_truthbrush_api(self):
        """初始化 truthbrush Api 实例，优先使用 token，其次用账号密码。"""
        from truthbrush.api import Api

        token    = os.environ.get("TRUTHSOCIAL_TOKEN")
        username = os.environ.get("TRUTHSOCIAL_USERNAME")
        password = os.environ.get("TRUTHSOCIAL_PASSWORD")

        if token:
            return Api(token=token)
        if username and password:
            return Api(username=username, password=password)
        raise RuntimeError(
            "缺少 Truth Social 凭据，请在 .env 中配置 TRUTHSOCIAL_TOKEN "
            "或 TRUTHSOCIAL_USERNAME + TRUTHSOCIAL_PASSWORD"
        )

    def fetch_from_truth_social(self, max_posts: int = 20, since_id: str = None) -> List[Dict[str, Any]]:
        """
        通过 truthbrush 获取 @realDonaldTrump 最新帖子。

        Args:
            max_posts:  最多返回条数
            since_id:   只返回比此 ID 更新的帖子（增量采集）
        """
        api = self._get_truthbrush_api()

        raw_posts = list(itertools.islice(
            api.pull_statuses(
                username=self.TRUTH_SOCIAL_USERNAME,
                replies=False,
                since_id=since_id,
            ),
            max_posts,
        ))

        statements = []
        for item in raw_posts[:max_posts]:
            # content 字段可能含 HTML，去除标签
            raw = item.get("content", "")
            content = re.sub(r"<[^>]+>", "", raw).strip()
            if not content:
                continue

            # 解析发帖时间
            created_at_raw = item.get("created_at", "")
            try:
                post_time = datetime.fromisoformat(
                    created_at_raw.replace("Z", "+00:00")
                ).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                post_time = datetime.now(timezone.utc)

            # 构造帖子 URL
            post_id = str(item.get("id", ""))
            url = item.get("url") or (
                f"https://truthsocial.com/@{self.TRUTH_SOCIAL_USERNAME}/{post_id}"
                if post_id else "https://truthsocial.com/@realDonaldTrump"
            )

            statements.append({
                "content":    content,
                "source":     "Truth Social",
                "post_time":  post_time,
                "likes":      item.get("favourites_count", 0),
                "shares":     item.get("reblogs_count", 0),
                "url":        url,
                "post_id":    post_id,
            })

        return statements

    def fetch_from_news(self) -> List[Dict[str, Any]]:
        """通过 NewsAPI 获取关于特朗普的最新新闻标题。"""
        if not self.news_api_key:
            raise RuntimeError("缺少 NEWS_API_KEY 环境变量，无法采集新闻数据")

        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "Donald Trump",
                "apiKey": self.news_api_key,
                "sortBy": "publishedAt",
                "pageSize": 10,
                "language": "en",
            },
            timeout=15,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])

        statements = []
        for article in articles:
            content = article.get("title") or article.get("description") or ""
            if not content:
                continue
            statements.append({
                "content": content,
                "source": article.get("source", {}).get("name", "Unknown"),
                "post_time": article.get("publishedAt") or datetime.utcnow().isoformat(),
                "url": article.get("url", ""),
            })
        return statements

    def fetch_data(self) -> Dict[str, Any]:
        all_statements = []

        try:
            ts_statements = self.fetch_from_truth_social()
            all_statements.extend(ts_statements)
            print(f"Truth Social 采集成功: {len(ts_statements)} 条")
        except Exception as e:
            print(f"Truth Social 采集失败: {e}")

        try:
            news_statements = self.fetch_from_news()
            all_statements.extend(news_statements)
            print(f"新闻采集成功: {len(news_statements)} 条")
        except Exception as e:
            print(f"新闻采集失败: {e}")

        if not all_statements:
            raise RuntimeError("所有数据源均采集失败，请检查 APIFY_TOKEN 和 NEWS_API_KEY")

        return {
            "statements": all_statements,
            "total": len(all_statements),
            "fetch_time": datetime.utcnow().isoformat(),
        }

    def preprocess(self, data: Dict[str, Any]) -> Dict[str, Any]:
        processed = super().preprocess(data)
        for stmt in processed["statements"]:
            sentiment, score = analyze_sentiment(stmt.get("content", ""))
            stmt["sentiment"] = sentiment
            stmt["sentiment_score"] = score
            # 规则法鹰派词汇计数
            stmt["hawkish_word_count"] = count_hawkish_words(stmt.get("content", ""))
            # 规则法鹰派评分（保底，保证所有言论都有评分，LLM成功后会覆盖）
            stmt["hawkish_score"] = analyze_hawkish_score(stmt.get("content", ""))
        # LLM 增强已移至 run_ingestion.py 中去重之后执行
        # 避免对已入库的重复数据调用大模型浪费 token
        return processed


# 导出采集器实例
TRUMP_STATEMENT_INGESTOR = TrumpStatementIngestor()


# ── 鹰派/鸽派倾向分析 ─────────────────────────────────────────

HAWKISH_RULES: List[Tuple[List[str], float]] = [
    # 直接军事威胁
    (["military strike", "bomb", "attack", "obliterate", "destroy", "fire and fury",
      "totally destroy", "wipe out", "annihilate", "shoot down", "shoot them down"], 1.0),
    # 极限施压
    (["maximum pressure", "sanctions", "tariff", "blockade", "embargo",
      "cut off", "choke", "strangle", "punish", "punishing"], 0.8),
    # 强硬威胁
    (["threat", "threaten", "warning", "warned", "ultimatum", "deadline",
      "consequences", "pay a price", "pay the price", "not going to allow"], 0.7),
    # 军事部署信号
    (["deploy", "troops", "military", "navy", "carrier", "warship", "missile",
      "nuclear", "arsenal", "force", "forces"], 0.6),
    # 强硬立场
    (["tough", "strong", "strength", "power", "powerful", "dominate",
      "win", "winning", "crush", "defeat", "enemy"], 0.5),
    # 中文鹰派词
    (["军事打击", "轰炸", "摧毁", "消灭", "极限施压", "制裁", "关税", "封锁",
      "威胁", "警告", "最后期限", "部署", "军队", "导弹", "核武器", "强硬"], 0.7),
]

DOVISH_RULES: List[Tuple[List[str], float]] = [
    # 谈判/外交
    (["negotiate", "negotiation", "deal", "agreement", "treaty", "accord",
      "diplomacy", "diplomatic", "dialogue", "talks", "meeting", "summit"], -0.8),
    # 和平信号
    (["peace", "peaceful", "ceasefire", "cease-fire", "truce", "de-escalate",
      "de-escalation", "withdraw", "withdrawal", "pullout"], -0.9),
    # 合作
    (["cooperate", "cooperation", "partner", "partnership", "ally", "alliance",
      "together", "joint", "mutual", "friendship"], -0.6),
    # 中文鸽派词
    (["谈判", "协议", "和平", "外交", "对话", "会谈", "峰会", "停火", "撤军",
      "合作", "伙伴", "友好", "协商"], -0.7),
]


def analyze_hawkish_score(text: str) -> float:
    """
    分析文本的鹰派倾向得分，返回 0–100。
    50 = 中性，>50 偏鹰派，<50 偏鸽派。
    """
    raw = 0.0
    text_lower = text.lower()

    for keywords, weight in HAWKISH_RULES:
        for kw in keywords:
            if kw in text_lower or kw in text:
                raw += weight
                break

    for keywords, weight in DOVISH_RULES:
        for kw in keywords:
            if kw in text_lower or kw in text:
                raw += weight  # weight 已为负数
                break

    # 强度修饰词
    intensifier = 1.0
    for word, factor in INTENSIFIERS.items():
        if word in text:
            intensifier = max(intensifier, factor)
    if raw != 0:
        raw *= intensifier

    # 归一化到 0-100，中性=50
    raw = max(-3.0, min(3.0, raw))
    score = (raw + 3.0) / 6.0 * 100
    return round(score, 2)
