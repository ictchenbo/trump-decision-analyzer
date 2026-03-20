"""
实时指标采集器 — 全部使用真实公开数据源，不生成随机数据。

数据源：
  - 布伦特原油 / 标普500 / 纳斯达克 / 道琼斯 / VIX / 国债：Yahoo Finance
  - 非农就业 / 失业率 / CPI：FRED API（需 FRED_API_KEY）
  - 特朗普支持率：Wikipedia 第二任期民调聚合页面
  - Polymarket 弹劾概率：Polymarket Gamma API
  - 地缘风险溢价（Brent-WTI价差）：Yahoo Finance
"""

import os
import re
import json
import requests
from datetime import datetime
from typing import Dict, Any

from .base_ingestor import BaseDataIngestor


# ── 工具函数 ──────────────────────────────────────────────────

def _yfinance_latest(ticker: str) -> float:
    """通过 Yahoo Finance v8 JSON API 获取最新收盘价/指数值，无需第三方库。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, params={"interval": "1d", "range": "5d"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    # 取最后一个非 None 值
    value = next(v for v in reversed(closes) if v is not None)
    return round(float(value), 4)


def _fred_latest(series_id: str, api_key: str) -> float:
    """从 FRED API 获取指定序列的最新观测值。"""
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 5,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    obs = resp.json()["observations"]
    for o in obs:
        if o["value"] != ".":
            return round(float(o["value"]), 4)
    raise ValueError(f"FRED {series_id}: 无有效观测值")


def _eia_latest(series_id: str, api_key: str) -> float:
    """从 EIA API v2 获取最新数据点。"""
    url = f"https://api.eia.gov/v2/seriesid/{series_id}"
    params = {"api_key": api_key, "data[0]": "value", "sort[0][column]": "period",
              "sort[0][direction]": "desc", "length": 1}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    rows = resp.json()["response"]["data"]
    if not rows:
        raise ValueError(f"EIA {series_id}: 无数据")
    return round(float(rows[0]["value"]), 4)


def _trump_approval_wikipedia() -> float:
    """
    从 Wikipedia「Opinion polling on the second Trump presidency」页面
    解析最新民调支持率，取最新日期所有机构的平均值。
    """
    resp = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "titles": "Opinion_polling_on_the_second_Trump_presidency",
            "prop": "revisions",
            "rvprop": "content",
            "format": "json",
            "rvlimit": 1,
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    resp.raise_for_status()
    pages = resp.json()["query"]["pages"]
    content = next(iter(pages.values()))["revisions"][0]["*"]

    lines = content.split("\n")
    # 逐行扫描：找日期行，然后取紧跟的 approve% 行
    MONTHS = ("January","February","March","April","May","June",
              "July","August","September","October","November","December")
    date_pat = re.compile(
        r"^\|\s*((?:" + "|".join(MONTHS) + r")\s+\d+,\s+\d{4}|\d{4}-\d{2}-\d{2})"
    )
    pct_pat = re.compile(r"^\|\s*(\d{2,3}(?:\.\d)?)\s*%")

    results: list[tuple[str, float]] = []
    i = 0
    while i < len(lines):
        dm = date_pat.match(lines[i].strip())
        if dm:
            date_str = dm.group(1)
            for j in range(i + 1, min(i + 6, len(lines))):
                pm = pct_pat.match(lines[j].strip())
                if pm:
                    results.append((date_str, float(pm.group(1))))
                    break
        i += 1

    if not results:
        raise ValueError("Wikipedia: 未找到 Trump approve 数据")

    # 取最新日期的所有值求平均
    latest_date = results[-1][0]
    latest_vals = [v for d, v in results if d == latest_date]
    return round(sum(latest_vals) / len(latest_vals), 2)


def _polymarket_price(slug: str) -> float:
    """
    从 Polymarket Gamma API 获取指定市场 Yes 的最新价格（0-100 百分比）。
    """
    resp = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={"slug": slug, "limit": 1},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    resp.raise_for_status()
    events = resp.json()
    if not events:
        raise ValueError(f"Polymarket: 未找到市场 {slug}")
    markets = events[0].get("markets", [])
    for mkt in markets:
        prices_raw = mkt.get("outcomePrices", "[]")
        outcomes_raw = mkt.get("outcomes", "[]")
        try:
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
        except Exception:
            continue
        for outcome, price in zip(outcomes, prices):
            if str(outcome).lower() == "yes":
                return round(float(price) * 100, 2)
    raise ValueError(f"Polymarket: {slug} 未找到 Yes 价格")


# ── 采集器类 ──────────────────────────────────────────────────

class BrentOilIngestor(BaseDataIngestor):
    """布伦特原油现货价 — Yahoo Finance (BZ=F)"""

    def __init__(self):
        super().__init__("brent_oil")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("BZ=F")
        return {"name": "布伦特原油期货", "value": value, "unit": "美元/桶",
                "trend": "unknown", "source": "Yahoo Finance (BZ=F)"}


class SP500Ingestor(BaseDataIngestor):
    """标普500指数 — Yahoo Finance (^GSPC)"""

    def __init__(self):
        super().__init__("sp500")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("^GSPC")
        return {"name": "标普500", "value": value, "unit": "点",
                "trend": "unknown", "source": "Yahoo Finance (^GSPC)"}


class TrumpApprovalIngestor(BaseDataIngestor):
    """特朗普支持率 — Wikipedia 第二任期民调聚合（多机构最新日期均值）"""

    def __init__(self):
        super().__init__("trump_approval")

    def fetch_data(self) -> Dict[str, Any]:
        value = _trump_approval_wikipedia()
        return {"name": "特朗普支持率", "value": value, "unit": "%",
                "trend": "unknown", "source": "Wikipedia / Opinion polling on second Trump presidency"}


class VIXIngestor(BaseDataIngestor):
    """CBOE波动率指数(VIX) — Yahoo Finance (^VIX)"""

    def __init__(self):
        super().__init__("vix")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("^VIX")
        return {"name": "波动率指数VIX", "value": value, "unit": "",
                "trend": "unknown", "source": "Yahoo Finance (^VIX)"}


class USTreasuryYieldIngestor(BaseDataIngestor):
    """美国10年期国债收益率 — Yahoo Finance (^TNX)"""

    def __init__(self):
        super().__init__("us_treasury_10y")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("^TNX")
        return {"name": "10年期国债收益率", "value": value, "unit": "%",
                "trend": "unknown", "source": "Yahoo Finance (^TNX)"}


class NonFarmPayrollIngestor(BaseDataIngestor):
    """
    非农就业月度新增人数 — FRED (PAYEMS)，需 FRED_API_KEY。
    取最近两期差值，反映当月新增/减少就业人数（千人）。
    月度新增 >200 = 强劲，100-200 = 正常，<100 = 疲软，负值 = 衰退信号。
    """

    def __init__(self):
        super().__init__("nonfarm_payroll")
        self.api_key = os.environ.get("FRED_API_KEY", "")

    def fetch_data(self) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("缺少 FRED_API_KEY 环境变量，无法获取非农就业数据")
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "PAYEMS",
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 2,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        obs = [o for o in resp.json()["observations"] if o["value"] != "."]
        if len(obs) < 2:
            raise ValueError("FRED PAYEMS: 数据不足以计算月度变化")
        latest = round(float(obs[0]["value"]), 1)
        prev   = round(float(obs[1]["value"]), 1)
        change = round(latest - prev, 1)
        return {"name": "非农就业", "value": change, "unit": "千人",
                "trend": "unknown", "source": "FRED PAYEMS (月度新增)"}


class UnemploymentRateIngestor(BaseDataIngestor):
    """美国失业率 — FRED (UNRATE)，需 FRED_API_KEY"""

    def __init__(self):
        super().__init__("unemployment_rate")
        self.api_key = os.environ.get("FRED_API_KEY", "")

    def fetch_data(self) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("缺少 FRED_API_KEY 环境变量，无法获取失业率数据")
        value = _fred_latest("UNRATE", self.api_key)
        return {"name": "失业率", "value": value, "unit": "%",
                "trend": "unknown", "source": "FRED UNRATE"}


class CPIIngestor(BaseDataIngestor):
    """美国CPI同比 — FRED (CPIAUCSL 同比计算)，需 FRED_API_KEY"""

    def __init__(self):
        super().__init__("cpi_yoy")
        self.api_key = os.environ.get("FRED_API_KEY", "")

    def fetch_data(self) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("缺少 FRED_API_KEY 环境变量，无法获取CPI数据")
        # 取最近13个月，计算同比
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "CPIAUCSL",
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 13,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        obs = [o for o in resp.json()["observations"] if o["value"] != "."]
        if len(obs) < 13:
            raise ValueError("FRED CPIAUCSL: 数据不足以计算同比")
        latest = float(obs[0]["value"])
        year_ago = float(obs[12]["value"])
        yoy = round((latest - year_ago) / year_ago * 100, 2)
        return {"name": "CPI同比", "value": yoy, "unit": "%",
                "trend": "unknown", "source": "FRED CPIAUCSL (同比计算)"}


class NasdaqIngestor(BaseDataIngestor):
    """纳斯达克综合指数 — Yahoo Finance (^IXIC)"""

    def __init__(self):
        super().__init__("nasdaq")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("^IXIC")
        return {"name": "纳斯达克指数", "value": value, "unit": "点",
                "trend": "unknown", "source": "Yahoo Finance (^IXIC)"}


class DowJonesIngestor(BaseDataIngestor):
    """道琼斯工业平均指数 — Yahoo Finance (^DJI)"""

    def __init__(self):
        super().__init__("dow_jones")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("^DJI")
        return {"name": "道琼斯指数", "value": value, "unit": "点",
                "trend": "unknown", "source": "Yahoo Finance (^DJI)"}


class HormuzTransitIngestor(BaseDataIngestor):
    """
    霍尔木兹海峡地缘风险代理指标 — 布伦特/WTI 价差（地缘溢价）。

    布伦特反映中东/全球供应风险，WTI 反映北美本地供需。
    价差扩大 → 中东地缘风险溢价上升。
    两者均来自 Yahoo Finance，无需额外 API key，实时性好。
    """

    def __init__(self):
        super().__init__("geopolitical_risk_premium")

    def fetch_data(self) -> Dict[str, Any]:
        brent = _yfinance_latest("BZ=F")   # 布伦特原油
        wti   = _yfinance_latest("CL=F")   # WTI 原油
        spread = round(brent - wti, 4)
        return {
            "name": "布油-WTI地缘溢价",
            "value": spread,
            "unit": "美元/桶",
            "trend": "unknown",
            "source": "Yahoo Finance Brent-WTI Spread (BZ=F - CL=F)",
        }


class PolymarketTrumpIngestor(BaseDataIngestor):
    """
    Polymarket 预测市场 — Trump 政治风险综合概率（聚合多个相关市场）。
    包括：弹劾、辞职、25条修正案、罢免等所有政治风险事件。
    按流动性加权平均，避免单一市场失效导致数据中断。
    """

    # 政治风险关键词
    RISK_KEYWORDS = ["impeach", "resign", "25th amendment", "removal", "removed from office", "leave office"]
    # 必须包含 Trump
    TRUMP_KEYWORDS = ["trump", "donald trump", "president trump"]

    def __init__(self):
        super().__init__("polymarket_trump_political_risk")

    def fetch_data(self) -> Dict[str, Any]:
        """聚合所有 Trump 政治风险市场"""
        resp = requests.get(
            "https://gamma-api.polymarket.com/events",
            params={"active": "true", "closed": "false", "limit": 100},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json()

        seen_event_ids = set()
        all_markets = []

        for event in events:
            event_id = event.get("id", "")
            if event_id in seen_event_ids:
                continue

            title = event.get("title", "").lower()
            description = event.get("description", "").lower()
            text = title + " " + description

            has_trump = any(kw in text for kw in self.TRUMP_KEYWORDS)
            has_risk = any(kw in text for kw in self.RISK_KEYWORDS)

            if not (has_trump and has_risk):
                continue

            seen_event_ids.add(event_id)

            for mkt in event.get("markets", []):
                try:
                    prices_raw = mkt.get("outcomePrices", "[]")
                    outcomes_raw = mkt.get("outcomes", "[]")
                    prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                    outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw

                    for outcome, price in zip(outcomes, prices):
                        if str(outcome).lower() == "yes":
                            liquidity = float(mkt.get("liquidity") or 0)
                            volume = float(mkt.get("volume") or 0)
                            weight = max(liquidity, volume, 1)
                            all_markets.append({
                                "price": float(price) * 100,
                                "weight": weight,
                                "title": event.get("title", ""),
                            })
                            break
                except Exception:
                    continue

        if not all_markets:
            raise RuntimeError("Polymarket: 未找到 Trump 政治风险相关市场")

        total_weight = sum(m["weight"] for m in all_markets)
        weighted_avg = sum(m["price"] * m["weight"] for m in all_markets) / total_weight

        return {
            "name": "Polymarket弹劾概率",
            "value": round(weighted_avg, 2),
            "unit": "%",
            "trend": "unknown",
            "source": f"Polymarket (聚合 {len(all_markets)} 个政治风险市场)",
        }


class PolymarketMilitaryStrikeIngestor(BaseDataIngestor):
    """
    Polymarket 预测市场 — 美国对外军事打击概率（聚合多个相关市场）。
    通过 Gamma API 的 tag/keyword 搜索，找到所有美国军事行动相关活跃市场，
    按流动性加权平均 Yes 价格。若无相关市场则静默跳过。
    """

    # 军事相关关键词，用于过滤标题
    MILITARY_KEYWORDS = ["military", "strike", "war", "attack", "invasion", "troops", "airstrike", "bomb", "conflict"]
    # 必须包含美国主体
    US_KEYWORDS = [" us ", "u.s.", "united states", "america", "american", "pentagon"]

    def __init__(self):
        super().__init__("polymarket_military_strike")

    def fetch_data(self) -> Dict[str, Any]:
        """一次性拉取活跃市场，过滤出美国军事行动相关条目，按流动性加权平均"""
        resp = requests.get(
            "https://gamma-api.polymarket.com/events",
            params={"active": "true", "closed": "false", "limit": 100},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json()

        seen_event_ids = set()
        all_markets = []

        for event in events:
            event_id = event.get("id", "")
            if event_id in seen_event_ids:
                continue

            title = event.get("title", "").lower()
            description = event.get("description", "").lower()
            text = title + " " + description

            has_military = any(kw in text for kw in self.MILITARY_KEYWORDS)
            has_us = any(kw in text for kw in self.US_KEYWORDS)

            if not (has_military and has_us):
                continue

            seen_event_ids.add(event_id)

            for mkt in event.get("markets", []):
                try:
                    prices_raw = mkt.get("outcomePrices", "[]")
                    outcomes_raw = mkt.get("outcomes", "[]")
                    prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
                    outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw

                    for outcome, price in zip(outcomes, prices):
                        if str(outcome).lower() == "yes":
                            liquidity = float(mkt.get("liquidity") or 0)
                            volume = float(mkt.get("volume") or 0)
                            weight = max(liquidity, volume, 1)
                            all_markets.append({
                                "price": float(price) * 100,
                                "weight": weight,
                                "title": event.get("title", ""),
                            })
                            break
                except Exception:
                    continue

        if not all_markets:
            raise RuntimeError("Polymarket: 未找到美国军事打击相关市场")

        total_weight = sum(m["weight"] for m in all_markets)
        weighted_avg = sum(m["price"] * m["weight"] for m in all_markets) / total_weight

        return {
            "name": "Polymarket军事打击概率",
            "value": round(weighted_avg, 2),
            "unit": "%",
            "trend": "unknown",
            "source": f"Polymarket (聚合 {len(all_markets)} 个市场)",
        }


class GoldPriceIngestor(BaseDataIngestor):
    """纽约黄金 — COMEX 黄金期货 (Yahoo Finance: GC=F)"""

    def __init__(self):
        super().__init__("gold_price")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("GC=F")
        return {"name": "纽约黄金", "value": value, "unit": "美元/盎司",
                "trend": "unknown", "source": "Yahoo Finance (GC=F)"}


class WTIOilIngestor(BaseDataIngestor):
    """纽约原油（WTI）— NYMEX 原油期货 (Yahoo Finance: CL=F)"""

    def __init__(self):
        super().__init__("wti_oil")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("CL=F")
        return {"name": "纽约原油", "value": value, "unit": "美元/桶",
                "trend": "unknown", "source": "Yahoo Finance (CL=F)"}


class USTreasury2YIngestor(BaseDataIngestor):
    """美国13周国债收益率（替代2年期）— Yahoo Finance (^IRX)"""

    def __init__(self):
        super().__init__("us_treasury_2y")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("^IRX")
        return {"name": "2年期国债收益率", "value": value, "unit": "%",
                "trend": "unknown", "source": "Yahoo Finance (^IRX)"}


class DollarIndexIngestor(BaseDataIngestor):
    """美元指数 — ICE Dollar Index (Yahoo Finance: DX-Y.NYB)"""

    def __init__(self):
        super().__init__("dollar_index")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("DX-Y.NYB")
        return {"name": "美元指数", "value": value, "unit": "",
                "trend": "unknown", "source": "Yahoo Finance (DX-Y.NYB)"}


class GasolineIngestor(BaseDataIngestor):
    """RBOB汽油期货 — NYMEX (Yahoo Finance: RB=F)"""

    def __init__(self):
        super().__init__("gasoline")

    def fetch_data(self) -> Dict[str, Any]:
        value = _yfinance_latest("RB=F")
        return {"name": "RBOB汽油价格", "value": value, "unit": "美元/加仑",
                "trend": "unknown", "source": "Yahoo Finance (RB=F)"}


# ── 采集器列表（无 API key 的采集器会在 run() 中记录错误，不影响其他采集器）──

ALL_INGESTORS = [
    BrentOilIngestor(),
    SP500Ingestor(),
    NasdaqIngestor(),
    DowJonesIngestor(),
    TrumpApprovalIngestor(),
    PolymarketTrumpIngestor(),
    PolymarketMilitaryStrikeIngestor(),
    VIXIngestor(),
    USTreasuryYieldIngestor(),
    USTreasury2YIngestor(),
    NonFarmPayrollIngestor(),
    UnemploymentRateIngestor(),
    CPIIngestor(),
    HormuzTransitIngestor(),
    GoldPriceIngestor(),
    WTIOilIngestor(),
    DollarIndexIngestor(),
    GasolineIngestor(),
]
