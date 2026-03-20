from datetime import datetime
from typing import Dict, Any, List
import numpy as np
from app.core.database import db
from app.ingestion.trump_statement_ingestor import analyze_hawkish_score


WAR_PEACE_LABELS = {
    "rhetoric": "言辞强硬度",
    "military_signal": "军事信号",
    "economic_pressure": "经济施压",
    "diplomatic_stance": "外交姿态",
    "domestic_motivation": "国内政治动机",
}

WAR_PEACE_WEIGHTS = {
    "rhetoric": 0.30,
    "military_signal": 0.25,
    "economic_pressure": 0.20,
    "diplomatic_stance": 0.15,
    "domestic_motivation": 0.10,
}


def _normalize(value: float, min_val: float, max_val: float, inverse: bool = False) -> float:
    score = (value - min_val) / (max_val - min_val) * 100
    score = float(np.clip(score, 0, 100))
    return round(100 - score if inverse else score, 2)


def compute_war_peace_scores(
    latest: Dict[str, float],
    recent_statements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    计算战争与和平指数各维度得分（0-100）和综合指数。
    分数越高表示越倾向于采取强硬/军事手段。
    """
    scores: Dict[str, float] = {}

    # ── 1. 言辞强硬度（rhetoric）────────────────────────────────
    # 取最近50条言论的 hawkish_score 均值
    if recent_statements:
        hawkish_scores = [
            analyze_hawkish_score(s.get("content", ""))
            for s in recent_statements[:50]
        ]
        scores["rhetoric"] = round(sum(hawkish_scores) / len(hawkish_scores), 2)
    else:
        scores["rhetoric"] = 50.0  # 无数据时中性

    # ── 2. 军事信号（military_signal）───────────────────────────
    # 布伦特油价 + Brent-WTI价差（地缘溢价）+ Polymarket军事打击概率
    military_parts = []
    if "布伦特原油" in latest:
        military_parts.append(_normalize(latest["布伦特原油"], 60, 130))
    if "地缘风险溢价" in latest:
        # Brent-WTI 价差（美元/桶），正常 2-6，地缘紧张时 10+
        military_parts.append(_normalize(latest["地缘风险溢价"], 0, 12))
    if "Polymarket军事打击概率" in latest:
        military_parts.append(_normalize(latest["Polymarket军事打击概率"], 0, 50))
    scores["military_signal"] = round(sum(military_parts) / len(military_parts), 2) if military_parts else 50.0

    # ── 3. 经济施压（economic_pressure）─────────────────────────
    # VIX（市场恐慌 → 施压信号）+ 关税/制裁言论词频
    econ_parts = []
    if "VIX指数" in latest:
        econ_parts.append(_normalize(latest["VIX指数"], 10, 40))
    # 关税/制裁词频：从最近言论中统计
    SANCTION_KEYWORDS = [
        "tariff", "tariffs", "sanction", "sanctions", "trade war",
        "关税", "制裁", "贸易战", "经济战", "封锁",
    ]
    if recent_statements:
        total_words = sum(len(s.get("content", "").split()) for s in recent_statements[:50]) or 1
        hit_count = sum(
            1
            for s in recent_statements[:50]
            for kw in SANCTION_KEYWORDS
            if kw.lower() in s.get("content", "").lower()
        )
        sanction_density = min(hit_count / len(recent_statements[:50]) * 100, 100)
        econ_parts.append(sanction_density)
    scores["economic_pressure"] = round(sum(econ_parts) / len(econ_parts), 2) if econ_parts else 50.0

    # ── 4. 外交姿态（diplomatic_stance）─────────────────────────
    # 支持率低 + 弹劾风险高 → 倾向对外强硬转移注意力
    diplo_parts = []
    if "特朗普支持率" in latest:
        # 支持率低 → 强硬动机强（反向）
        diplo_parts.append(_normalize(latest["特朗普支持率"], 30, 60, inverse=True))
    if "Polymarket弹劾概率" in latest:
        # 弹劾概率高 → 强硬动机强（正向）
        diplo_parts.append(_normalize(latest["Polymarket弹劾概率"], 0, 30))
    scores["diplomatic_stance"] = round(sum(diplo_parts) / len(diplo_parts), 2) if diplo_parts else 50.0

    # ── 5. 国内政治动机（domestic_motivation）───────────────────
    # 失业率高 + CPI高 → 经济压力大 → 对外强硬动机强
    dom_parts = []
    if "失业率" in latest:
        dom_parts.append(_normalize(latest["失业率"], 3.0, 6.0))
    if "CPI同比" in latest:
        dom_parts.append(_normalize(latest["CPI同比"], 1.5, 5.0))
    scores["domestic_motivation"] = round(sum(dom_parts) / len(dom_parts), 2) if dom_parts else 50.0

    # ── 综合指数（加权平均）──────────────────────────────────────
    total_w = sum(WAR_PEACE_WEIGHTS.values())
    composite = sum(
        scores[f] * WAR_PEACE_WEIGHTS[f] / total_w
        for f in WAR_PEACE_WEIGHTS
    )
    composite_index = round(float(np.clip(composite, 0, 100)), 2)

    return {
        "factor_scores": scores,
        "composite_index": composite_index,
        "weights": WAR_PEACE_WEIGHTS,
        "computed_at": datetime.utcnow(),
        "raw_indicators": {k: v for k, v in latest.items()},
    }


def run_war_peace_ingestor():
    """从 real_time_data 和 trump_statements 取最新数据，计算战争与和平指数并写入 war_peace_scores 集合"""
    # 取各实时指标最新值
    pipeline = [
        {"$sort": {"updated_at": -1}},
        {"$group": {"_id": "$name", "value": {"$first": "$value"}}},
    ]
    latest = {
        doc["_id"]: doc["value"]
        for doc in db.db["real_time_data"].aggregate(pipeline)
        if doc["_id"] is not None and doc["value"] is not None
    }

    if not latest:
        return None

    # 取最近50条言论
    recent_statements = list(
        db.db["trump_statements"]
        .find({}, {"content": 1, "_id": 0})
        .sort("post_time", -1)
        .limit(50)
    )

    result = compute_war_peace_scores(latest, recent_statements)
    db.db["war_peace_scores"].insert_one(result)
    return result
