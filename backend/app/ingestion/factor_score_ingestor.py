from datetime import datetime
from typing import Dict, Any
import numpy as np
from app.core.database import db


# 各因子的指标映射及归一化参数
# (指标名, 正向/反向影响, 参考最小值, 参考最大值)
FACTOR_INDICATOR_MAP = {
    "geopolitical": [
        # 地缘风险溢价（Brent-WTI价差，美元/桶），价差越大 → 地缘风险越高
        # 正常价差 2-6 美元，地缘紧张时可达 10+ 美元
        ("布油-WTI地缘溢价", "direct", 0, 12),
        ("布伦特原油期货", "direct", 60, 130),
        ("纽约黄金", "direct", 1800, 3200),
    ],
    "domestic_political": [
        ("特朗普支持率", "direct", 30, 60),
        # Polymarket 弹劾概率高 → 国内政治压力大（正向）
        ("Polymarket弹劾概率", "direct", 0, 30),
    ],
    "financial_market": [
        ("纳斯达克指数", "inverse", 12000, 20000),
        ("道琼斯指数", "inverse", 32000, 45000),
        ("波动率指数VIX", "direct", 10, 40),
        # 国债收益率高 → 金融市场压力大（正向）
        ("10年期国债收益率", "direct", 3.0, 5.5),
        # 美元指数强 → 金融市场鹰派预期升温（正向）
        ("美元指数", "direct", 90, 110),
    ],
    "energy_market": [
        ("布伦特原油期货", "direct", 60, 130),
        ("纽约原油期货", "direct", 55, 125),
        ("RBOB汽油价格", "direct", 2, 4),
        ("CPI同比", "direct", 1.5, 5.0),
    ],
    "decision_team": [
        ("特朗普支持率", "direct", 30, 60),
    ],
}

FACTOR_LABELS = {
    "geopolitical": "地缘政治",
    "domestic_political": "国内政治",
    "financial_market": "金融市场",
    "energy_market": "能源市场",
    "decision_team": "决策团队",
}

BASE_WEIGHTS = {
    "geopolitical": 0.2,
    "domestic_political": 0.3,
    "financial_market": 0.25,
    "energy_market": 0.15,
    "decision_team": 0.1,
}


def _normalize(value: float, min_val: float, max_val: float, inverse: bool) -> float:
    """将原始值归一化到 0-100"""
    score = (value - min_val) / (max_val - min_val) * 100
    score = float(np.clip(score, 0, 100))
    return round(100 - score if inverse else score, 2)


def compute_factor_scores(latest: Dict[str, float]) -> Dict[str, Any]:
    """
    根据最新实时指标计算各因子得分（0-100）和综合指数。
    latest: {指标名: 最新值}
    """
    factor_scores = {}
    for factor, indicators in FACTOR_INDICATOR_MAP.items():
        scores = []
        for name, direction, min_v, max_v in indicators:
            if name in latest:
                s = _normalize(latest[name], min_v, max_v, direction == "inverse")
                scores.append(s)
        factor_scores[factor] = round(sum(scores) / len(scores), 2) if scores else 50.0

    # 计算综合指数（加权平均，映射到 0-100）
    total_w = sum(BASE_WEIGHTS.values())
    composite = sum(
        factor_scores[f] * BASE_WEIGHTS[f] / total_w
        for f in BASE_WEIGHTS
    )
    composite_index = round(float(np.clip(composite, 0, 100)), 2)

    return {
        "factor_scores": factor_scores,
        "composite_index": composite_index,
        "weights": BASE_WEIGHTS,
        "computed_at": datetime.utcnow(),
        "raw_indicators": latest,
    }


def run_factor_score_ingestor():
    """从 real_time_data 取最新指标，计算因子得分并写入 factor_scores 集合"""
    collection = db.db["real_time_data"]

    # 每个指标取最新一条
    pipeline = [
        {"$sort": {"updated_at": -1}},
        {"$group": {
            "_id": "$name",
            "value": {"$first": "$value"},
        }},
    ]
    latest = {
        doc["_id"]: doc["value"]
        for doc in collection.aggregate(pipeline)
        if doc["_id"] is not None and doc["value"] is not None
    }

    if not latest:
        return None

    result = compute_factor_scores(latest)
    db.db["factor_scores"].insert_one(result)
    return result
