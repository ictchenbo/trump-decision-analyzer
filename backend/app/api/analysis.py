from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from app.models.decision_event import FactorScore
from app.core.database import db
import numpy as np
from bson.objectid import ObjectId
from bson.errors import InvalidId
from app.ingestion.factor_score_ingestor import FACTOR_LABELS, BASE_WEIGHTS
from app.ingestion.war_peace_ingestor import WAR_PEACE_LABELS, WAR_PEACE_WEIGHTS

router = APIRouter(prefix="/analysis", tags=["analysis"])

def _dt_to_utcz(v: datetime) -> str:
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def _serialize(obj):
    """递归将 dict/list 中的 datetime 转为带 Z 的 UTC 字符串"""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, datetime):
        return _dt_to_utcz(obj)
    return obj

@router.post("/composite-index", response_model=dict)
async def calculate_composite_index(factor_scores: FactorScore, context: Optional[Dict] = None):
    """
    计算综合影响指数
    - **factor_scores**: 各因子得分
    - **context**: 上下文参数（如选举周期、油价高位等）
    """
    # 基础权重配置
    base_weights = {
        "geopolitical": 0.2,
        "domestic_political": 0.3,
        "financial_market": 0.25,
        "energy_market": 0.15,
        "decision_team": 0.1
    }
    
    # 根据上下文动态调整权重
    if context:
        # 选举前6个月：国内政治权重+30%
        if context.get("election_period"):
            base_weights["domestic_political"] *= 1.3
        # 油价>100美元：能源市场权重+25%
        if context.get("high_oil_price"):
            base_weights["energy_market"] *= 1.25
        # 股市暴跌：金融市场权重+20%
        if context.get("market_crash"):
            base_weights["financial_market"] *= 1.2
    
    # 归一化权重
    total_weight = sum(base_weights.values())
    dynamic_weights = {k: v / total_weight for k, v in base_weights.items()}
    
    # 计算综合指数
    composite = 0
    for factor, score in factor_scores.model_dump().items():
        composite += score * dynamic_weights.get(factor, 0)
    
    composite_index = np.clip(composite * 100 / 5, 0, 100)
    
    return {
        "composite_index": round(composite_index, 2),
        "dynamic_weights": dynamic_weights,
        "factor_scores": factor_scores.model_dump()
    }

@router.get("/timeline/{event_id}", response_model=dict)
async def get_event_timeline(event_id: str):
    """
    获取指定事件的时间轴
    """
    try:
        oid = ObjectId(event_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid event_id format")
    collection = db.db["decision_events"]
    event = collection.find_one({"_id": oid})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event["_id"] = str(event["_id"])
    # 获取相关的时间序列数据
    data_collection = db.db["real_time_data"]
    related_data = list(data_collection.find({
        "updated_at": {
            "$gte": event["event_time"] - timedelta(hours=24),
            "$lte": event["event_time"] + timedelta(hours=24)
        }
    }, {"_id": 0}).limit(100))
    
    return {
        "event": event,
        "related_data": related_data
    }

@router.post("/simulate", response_model=dict)
async def run_simulation(factor: str, adjustment: float, base_index: float):
    """
    运行反事实模拟
    - **factor**: 要调整的因子
    - **adjustment**: 调整幅度（百分比）
    - **base_index": 基础综合指数
    """
    # 简单模拟：调整指定因子的权重，重新计算指数
    simulation_weights = {
        "geopolitical": 0.2,
        "domestic_political": 0.3,
        "financial_market": 0.25,
        "energy_market": 0.15,
        "decision_team": 0.1
    }
    
    # 调整指定因子
    if factor in simulation_weights:
        simulation_weights[factor] *= (1 + adjustment / 100)
    
    # 归一化
    total = sum(simulation_weights.values())
    normalized = {k: v / total for k, v in simulation_weights.items()}
    
    # 假设基础因子得分
    base_scores = {
        "geopolitical": 78,
        "domestic_political": 65,
        "financial_market": 82,
        "energy_market": 90,
        "decision_team": 55
    }
    
    # 计算模拟指数
    simulated = 0
    for k, v in base_scores.items():
        simulated += v * normalized.get(k, 0)
    simulated_index = np.clip(simulated * 100 /5, 0, 100)
    
    return {
        "original_index": base_index,
        "simulated_index": round(simulated_index, 2),
        "adjusted_factor": factor,
        "adjustment": adjustment
    }


@router.get("/factor-scores/latest", response_model=dict)
async def get_latest_factor_scores():
    """
    获取最新一次计算的因子得分和综合指数
    """
    doc = db.db["factor_scores"].find_one({}, {"_id": 0}, sort=[("computed_at", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="No factor scores available yet")

    # 附加中文标签和权重
    scores = doc.get("factor_scores", {})
    detail = [
        {
            "key": k,
            "label": FACTOR_LABELS.get(k, k),
            "score": scores.get(k, 0),
            "weight": round(BASE_WEIGHTS.get(k, 0) * 100, 1),
        }
        for k in BASE_WEIGHTS
    ]
    # computed_at 转带 Z 的 UTC 字符串
    if "computed_at" in doc and isinstance(doc["computed_at"], datetime):
        doc["computed_at"] = _dt_to_utcz(doc["computed_at"])

    return _serialize({**doc, "detail": detail})


@router.get("/factor-scores/history", response_model=list)
async def get_factor_scores_history(limit: int = 200):
    """
    获取因子得分历史，用于趋势展示
    """
    # 返回从2026-02-28以来的所有历史数据
    since = datetime(2026, 2, 28, 0, 0, 0, tzinfo=timezone.utc)
    cursor = db.db["factor_scores"]\
        .find({"computed_at": {"$gte": since}}, {"_id": 0})\
        .sort("computed_at", -1)\
        .limit(limit)
    result = [_serialize(doc) for doc in cursor]
    return list(reversed(result))


@router.get("/war-peace/latest", response_model=dict)
async def get_latest_war_peace_scores():
    """
    获取最新一次计算的战争与和平指数
    """
    doc = db.db["war_peace_scores"].find_one({}, {"_id": 0}, sort=[("computed_at", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="No war-peace scores available yet")

    scores = doc.get("factor_scores", {})
    detail = [
        {
            "key": k,
            "label": WAR_PEACE_LABELS.get(k, k),
            "score": scores.get(k, 0),
            "weight": round(WAR_PEACE_WEIGHTS.get(k, 0) * 100, 1),
        }
        for k in WAR_PEACE_WEIGHTS
    ]
    if "computed_at" in doc and isinstance(doc["computed_at"], datetime):
        doc["computed_at"] = _dt_to_utcz(doc["computed_at"])

    return _serialize({**doc, "detail": detail})


@router.get("/war-peace/history", response_model=list)
async def get_war_peace_history(limit: int = 200):
    """
    获取战争与和平指数历史，用于趋势展示
    """
    # 返回从2026-02-28以来的所有历史数据
    since = datetime(2026, 2, 28, 0, 0, 0, tzinfo=timezone.utc)
    cursor = db.db["war_peace_scores"]\
        .find({"computed_at": {"$gte": since}}, {"_id": 0})\
        .sort("computed_at", -1)\
        .limit(limit)
    result = [_serialize(doc) for doc in cursor]
    return list(reversed(result))


@router.get("/regression", response_model=dict)
async def get_regression_analysis(
    y_type: str = "hawkish_mean",
    hawkish_threshold: int = 60,
    lag_filter: str = "all",
    analysis_mode: str = "original"  # "original" = X指标→Y鹰派; "swap" = X鹰派→Y指标; "hawkish_lag1" = X鹰派滞后1天→Y指标
):
    """
    相关性分析，支持多种分析模式：
    1. original: 关键指标（X）→ Truth Social 政策评分（Y）- 市场影响鹰派
    2. swap: 政策评分（X）→ 关键指标（Y）- 鹰派言论影响市场
    3. hawkish_lag1: 政策评分滞后1天（X）→ 关键指标（Y）- 昨日鹰派影响今日市场

    参数：
    - y_type: 选择因变量 Y 的计算方式 (original模式下):
      - hawkish_mean = 当日政策评分均值（默认）
      - hawkish_max = 当日政策评分最大值
      - hawkish_ratio = 当日鹰派帖子占比（score >= hawkish_threshold）
      - post_count = 当日帖子数量
      - hawkish_word_avg = 当日鹰派词汇平均计数
    - hawkish_threshold: 判定为鹰派帖子的分数阈值，默认 60
    - lag_filter: 滞后指标筛选:
      - all = 显示全部指标（默认）
      - none = 只显示无滞后原始指标
      - lag1 = 只显示滞后1天指标
      - lag3 = 只显示滞后3天指标
      - lag7 = 只显示滞后7天指标
    - analysis_mode: 分析模式
      - original: X市场 → Y鹰派（默认）
      - swap: X鹰派 → Y市场（XY互换）
      - hawkish_lag1: X鹰派滞后1天 → Y市场（分析鹰派对次日市场影响）
    """
    since = datetime(2026, 2, 28, tzinfo=timezone.utc)

    # ── 1. 按日聚合 Y：Truth Social 政策评分多个统计量 ──────────────────
    ts_col = db.db["trump_statements"]
    iran_keywords = ["Iran", "oil", "petroleum", "Hormuz", "sanction", "energy", "OPEC", "nuclear"]
    regex = "|".join(iran_keywords)

    pipeline_y = [
        {"$match": {
            "source": "Truth Social",
            "post_time": {"$gte": since},
            "hawkish_score": {"$exists": True, "$ne": None},
            "content": {"$regex": regex, "$options": "i"},
        }},
        {"$group": {
            "_id": {
                "y": {"$year": "$post_time"},
                "m": {"$month": "$post_time"},
                "d": {"$dayOfMonth": "$post_time"},
            },
            "hawkish_avg": {"$avg": "$hawkish_score"},
            "hawkish_max": {"$max": "$hawkish_score"},
            "word_count_sum": {"$sum": "$hawkish_word_count"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    # 先取出所有分数列表在Python端计算比例
    pipeline_all = [
        {"$match": {
            "source": "Truth Social",
            "post_time": {"$gte": since},
            "hawkish_score": {"$exists": True, "$ne": None},
            "content": {"$regex": regex, "$options": "i"},
        }},
        {"$project": {
            "year": {"$year": "$post_time"},
            "month": {"$month": "$post_time"},
            "day": {"$dayOfMonth": "$post_time"},
            "score": "$hawkish_score",
        }},
    ]

    y_by_day = {}
    # 先用aggregate获取基本统计量
    for doc in ts_col.aggregate(pipeline_y):
        day = f"{doc['_id']['y']:04d}-{doc['_id']['m']:02d}-{doc['_id']['d']:02d}"
        word_count_avg = round(doc["word_count_sum"] / doc["count"], 2) if doc["count"] > 0 else 0
        y_by_day[day] = {
            "hawkish_avg": round(doc["hawkish_avg"], 2),
            "hawkish_max": round(doc["hawkish_max"], 2),
            "post_count": doc["count"],
            "hawkish_word_avg": word_count_avg,
            "scores": [],
        }

    # 然后填充所有分数进去计算比例
    for doc in ts_col.aggregate(pipeline_all):
        day = f"{doc['year']:04d}-{doc['month']:02d}-{doc['day']:02d}"
        if day in y_by_day:
            y_by_day[day]["scores"].append(doc["score"])

    # 计算鹰派比例
    for day in y_by_day:
        scores = y_by_day[day]["scores"]
        hawkish_count = sum(1 for s in scores if s >= hawkish_threshold)
        y_by_day[day]["hawkish_ratio"] = round(hawkish_count / len(scores), 4) if scores else 0

    if len(y_by_day) < 3:
        raise HTTPException(status_code=404, detail="数据不足，至少需要 3 个有效交易日")

    # ── 2. 按日聚合 X：factor_scores.raw_indicators 各指标均值 ────
    fs_col = db.db["factor_scores"]
    pipeline_x = [
        {"$match": {"computed_at": {"$gte": since}, "raw_indicators": {"$exists": True}}},
        {"$group": {
            "_id": {
                "y": {"$year": "$computed_at"},
                "m": {"$month": "$computed_at"},
                "d": {"$dayOfMonth": "$computed_at"},
            },
            "raw_indicators": {"$last": "$raw_indicators"},
        }},
        {"$sort": {"_id": 1}},
    ]
    x_by_day = {}
    for doc in fs_col.aggregate(pipeline_x):
        day = f"{doc['_id']['y']:04d}-{doc['_id']['m']:02d}-{doc['_id']['d']:02d}"
        x_by_day[day] = doc["raw_indicators"]

    # 指标中文名映射（与 raw_indicators 存储的 key 对应）
    INDICATOR_LABELS = {
        "标普500":                "标普500",
        "布伦特原油期货":         "布伦特原油期货",
        "纽约原油期货":           "纽约原油期货(WTI)",
        "波动率指数VIX":          "波动率指数VIX",
        "10年期国债收益率":        "10年期国债收益率",
        "2年期国债收益率":        "2年期国债收益率",
        "特朗普支持率":           "支持率",
        "纽约黄金":               "纽约黄金(COMEX)",
        "布油-WTI地缘溢价":       "布油-WTI地缘溢价",
        # "CPI同比":               "CPI同比",
        "Polymarket弹劾概率":     "弹劾概率",
        "纳斯达克指数":           "纳斯达克指数",
        "道琼斯指数":             "道琼斯指数",
        "美元指数":               "美元指数",
        "RBOB汽油价格":           "RBOB汽油价格",
    }

    # ── 根据分析模式处理数据 ─────────────────────────────────────────
    # 初始共同日期
    common_days = sorted(set(y_by_day) & set(x_by_day))
    if len(common_days) < 3:
        raise HTTPException(status_code=404, detail="交集数据不足，至少需要 3 个有效交易日")

    if analysis_mode == "original":
        # 原始模式：X(市场) → Y(鹰派)
        # 添加市场指标的滞后变量：X(t-k)
        LAGS = [1, 3, 7]
        for i, day in enumerate(common_days):
            for lag in LAGS:
                if i < lag:
                    continue
                prev_day = common_days[i - lag]
                for ind in x_by_day[prev_day]:
                    if ind in INDICATOR_LABELS and "_lag" not in ind:
                        val = x_by_day[prev_day][ind]
                        lag_ind = f"{ind}_lag{lag}"
                        x_by_day[day][lag_ind] = val
                        INDICATOR_LABELS[lag_ind] = f"{INDICATOR_LABELS[ind]} 滞后{lag}天"

        # 收集所有指标
        all_indicators = set()
        for day in common_days:
            all_indicators.update(x_by_day[day].keys())

        Y_LABELS = {
            "hawkish_mean": "政策评分均值",
            "hawkish_max": "政策评分最大值",
            "hawkish_ratio": "鹰派帖子比例",
            "post_count": "发帖数量",
            "hawkish_word_avg": "鹰派词汇均值",
        }
        y_label = Y_LABELS.get(y_type, Y_LABELS["hawkish_mean"])

    elif analysis_mode in ["swap", "hawkish_lag1"]:
        # XY互换模式 / 鹰派滞后1天模式：X(鹰派) → Y(市场)
        common_days = sorted(set(y_by_day) & set(x_by_day))
        if len(common_days) < 3:
            raise HTTPException(status_code=404, detail="交集数据不足，至少需要 3 个有效交易日")

        # 将政策评分作为X，添加到x_by_day
        all_indicators = set(INDICATOR_LABELS.keys())  # 所有市场指标作为Y的候选

        # 如果是滞后1天模式，需要构建滞后政策评分：鹰派(t) → 市场(t+1)
        if analysis_mode == "hawkish_lag1":
            # 为每个交易日添加前一天的政策评分作为X
            for i, day in enumerate(common_days):
                if i >= 1:
                    prev_day = common_days[i - 1]
                    # 将前一天的政策评分添加到当前day的X池中
                    y_data = y_by_day[prev_day]
                    for y_key in ["hawkish_avg", "hawkish_max", "hawkish_ratio", "post_count", "hawkish_word_avg"]:
                        x_key = f"{y_key}_hawkish_lag1"
                        x_by_day[day][x_key] = y_data[y_key]
                        # 添加标签
                        if y_key == "hawkish_avg":
                            INDICATOR_LABELS[x_key] = f"政策评分均值(滞后1天)"
                        elif y_key == "hawkish_max":
                            INDICATOR_LABELS[x_key] = f"政策评分最大值(滞后1天)"
                        elif y_key == "hawkish_ratio":
                            INDICATOR_LABELS[x_key] = f"鹰派帖子比例(滞后1天)"
                        elif y_key == "post_count":
                            INDICATOR_LABELS[x_key] = f"发帖数量(滞后1天)"
                        elif y_key == "hawkish_word_avg":
                            INDICATOR_LABELS[x_key] = f"鹰派词汇均值(滞后1天)"
                        all_indicators.add(x_key)
        else:  # swap 模式 - XY互换
            # 将当日政策评分作为X
            for i, day in enumerate(common_days):
                y_data = y_by_day[day]
                for y_key in ["hawkish_avg", "hawkish_max", "hawkish_ratio", "post_count", "hawkish_word_avg"]:
                    x_key = f"{y_key}_hawkish"
                    x_by_day[day][x_key] = y_data[y_key]
                    # 添加标签
                    if y_key == "hawkish_avg":
                        INDICATOR_LABELS[x_key] = f"政策评分均值"
                    elif y_key == "hawkish_max":
                        INDICATOR_LABELS[x_key] = f"政策评分最大值"
                    elif y_key == "hawkish_ratio":
                        INDICATOR_LABELS[x_key] = f"鹰派帖子比例"
                    elif y_key == "post_count":
                        INDICATOR_LABELS[x_key] = f"发帖数量"
                    elif y_key == "hawkish_word_avg":
                        INDICATOR_LABELS[x_key] = f"鹰派词汇均值"
                    all_indicators.add(x_key)

        # 对于swap和hawkish_lag1，Y就是市场指标
        Y_LABELS = {ind: label for ind, label in INDICATOR_LABELS.items() if not ind.endswith('hawkish') and not ind.endswith('hawkish_lag1')}
        # 使用传入的y_type作为目标Y（此时y_type实际上是市场指标key）
        y_label = INDICATOR_LABELS.get(y_type, y_type) if y_type in INDICATOR_LABELS else "市场指标"

    else:
        raise HTTPException(status_code=400, detail=f"不支持的分析模式: {analysis_mode}")

    # 根据 lag_filter 过滤指标（仅original模式有效）
    filtered_indicators = []
    if analysis_mode == "original":
        for ind in sorted(all_indicators):
            if ind not in INDICATOR_LABELS:
                continue
            if lag_filter == "all":
                filtered_indicators.append(ind)
            elif lag_filter == "none":
                if "_lag" not in ind:
                    filtered_indicators.append(ind)
            else:
                if f"_{lag_filter}" in ind:
                    filtered_indicators.append(ind)
    else:
        # swap和hawkish_lag1模式：只显示鹰派相关X指标
        for ind in sorted(all_indicators):
            if ind not in INDICATOR_LABELS:
                continue
            if analysis_mode == "swap" and ind.endswith('_hawkish'):
                filtered_indicators.append(ind)
            elif analysis_mode == "hawkish_lag1" and ind.endswith('_lag1'):
                filtered_indicators.append(ind)

    results = {}

    for ind in filtered_indicators:
        if ind not in INDICATOR_LABELS:
            continue
        x_vals = []
        y_vals = []
        points = []
        last_known = None

        for day in common_days:
            xv = x_by_day[day].get(ind)
            if xv is not None:
                last_known = xv
            elif last_known is not None:
                xv = last_known
            if xv is None:
                continue

            # 根据模式获取Y值
            if analysis_mode == "original":
                # 原始模式：Y是政策评分
                y_val = y_by_day[day].get(y_type, y_by_day[day]["hawkish_avg"])
            else:
                # swap/hawkish_lag1模式：Y是市场指标
                y_val = x_by_day[day].get(y_type)
                if y_val is None:
                    continue
                y_val = float(y_val)

            x_vals.append(float(xv))
            y_vals.append(y_val)
            points.append({"date": day, "x": round(float(xv), 4), "y": round(y_val, 4)})

        if len(x_vals) < 3:
            continue

        x_arr = np.array(x_vals)
        y_arr_sub = np.array(y_vals)

        # 线性回归 y = a*x + b
        coeffs = np.polyfit(x_arr, y_arr_sub, 1)
        a, b = float(coeffs[0]), float(coeffs[1])

        # R²
        y_pred = a * x_arr + b
        ss_res = float(np.sum((y_arr_sub - y_pred) ** 2))
        ss_tot = float(np.sum((y_arr_sub - np.mean(y_arr_sub)) ** 2))
        r2 = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0

        # 相关系数
        corr_raw = float(np.corrcoef(x_arr, y_arr_sub)[0, 1]) if len(x_vals) > 1 else 0.0
        if np.isnan(corr_raw):
            continue
        corr = corr_raw

        # 回归线端点
        x_min, x_max = float(x_arr.min()), float(x_arr.max())
        results[ind] = {
            "label": INDICATOR_LABELS.get(ind, ind),
            "a": round(a, 6),
            "b": round(b, 4),
            "r2": r2,
            "corr": round(corr, 4),
            "n": len(x_vals),
            "x_min": round(x_min, 4),
            "x_max": round(x_max, 4),
            "y_at_xmin": round(a * x_min + b, 2),
            "y_at_xmax": round(a * x_max + b, 2),
            "points": points,
        }

    # 按 |r| 降序排列
    sorted_results = dict(
        sorted(results.items(), key=lambda kv: abs(kv[1]["corr"]), reverse=True)
    )

    # 准备Y选项列表 - 根据分析模式返回不同的选项
    if analysis_mode == "original":
        y_options = [
            {"key": "hawkish_mean", "label": "政策评分均值"},
            # {"key": "hawkish_max", "label": "政策评分最大值"},
            {"key": "hawkish_ratio", "label": "鹰派帖子比例"},
            # {"key": "post_count", "label": "发帖数量"},
            {"key": "hawkish_word_avg", "label": "鹰派词汇均值"},
        ]
    else:
        # swap/hawkish_lag1模式：Y选项是各个市场指标
        y_options = [
            {"key": "标普500", "label": "标普500"},
            {"key": "纳斯达克指数", "label": "纳斯达克"},
            {"key": "道琼斯指数", "label": "道琼斯"},
            {"key": "布伦特原油期货", "label": "布伦特原油"},
            {"key": "纽约原油期货", "label": "纽约原油"},
            {"key": "波动率指数VIX", "label": "波动率指数VIX"},
            {"key": "布油-WTI地缘溢价", "label": "布油-WTI地缘溢价"},
            {"key": "RBOB汽油价格", "label": "RBOB汽油价格"},
            {"key": "美元指数", "label": "美元指数"},
            {"key": "10年期国债收益率", "label": "10年期国债收益率"},
            {"key": "2年期国债收益率", "label": "2年期国债收益率"},
            {"key": "纽约黄金", "label": "纽约黄金"},
            # {"key": "CPI同比", "label": "CPI同比"},
            {"key": "特朗普支持率", "label": "支持率"},
            {"key": "Polymarket弹劾概率", "label": "弹劾概率"},
        ]

    return {
        "since": since.strftime("%Y-%m-%d"),
        "days": len(common_days),
        "y_type": y_type,
        "y_label": y_label,
        "y_options": y_options,
        "indicators": sorted_results,
        "analysis_mode": analysis_mode,
    }