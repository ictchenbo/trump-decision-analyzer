from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from app.models.decision_event import DecisionEvent, FactorScore, RealTimeData
from app.core.database import db

router = APIRouter(prefix="/data", tags=["data"])

def _serialize(obj):
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, datetime):
        v = obj.replace(tzinfo=timezone.utc) if obj.tzinfo is None else obj
        return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return obj

@router.get("/real-time/history", response_model=List[dict])
async def get_real_time_history(
    indicator: str = Query(..., description="指标名称"),
    granularity: str = Query(default="day", description="粒度: minute | hour | day | week"),
    limit: int = Query(default=60, ge=1, le=1000)
):
    """
    获取指定指标的历史时间序列，支持 minute/hour/day/week 粒度聚合。
    minute/hour 粒度只返回当前交易日（美东时间 09:30-16:00）的数据。
    """
    collection = db.db["real_time_data"]

    GRANULARITY_SECONDS = {
        "minute": 60,
        "hour":   3600,
        "day":    86400,
        "week":   604800,
    }
    bucket_secs = GRANULARITY_SECONDS.get(granularity, 86400)

    # 分钟/小时粒度：只取当前交易日数据
    # 美东时间 = UTC-5（EST）/ UTC-4（EDT），美股交易时间 09:30-16:00 ET
    # 用 UTC 表示：EST 09:30 = UTC 14:30，EDT 09:30 = UTC 13:30
    # 保守取 UTC 13:00 作为当日开盘起点，UTC 21:00 作为收盘终点
    match_filter: dict = {"name": indicator}
    if granularity in ("minute", "hour"):
        now_utc = datetime.now(timezone.utc)
        # 找最近的交易日开盘时间（UTC 13:00，对应 ET 09:00 含盘前）
        trading_day_start = now_utc.replace(hour=13, minute=0, second=0, microsecond=0)
        # 若当前时间早于今日 UTC 13:00，则取前一天
        if now_utc < trading_day_start:
            trading_day_start -= timedelta(days=1)
        # 跳过周末（周六=5，周日=6）
        while trading_day_start.weekday() >= 5:
            trading_day_start -= timedelta(days=1)
        match_filter["updated_at"] = {"$gte": trading_day_start}

    pipeline = [
        {"$match": match_filter},
        {"$sort": {"updated_at": 1}},
        {"$group": {
            "_id": {
                "$subtract": [
                    {"$toLong": "$updated_at"},
                    {"$mod": [{"$toLong": "$updated_at"}, bucket_secs * 1000]}
                ]
            },
            "value":      {"$last": "$value"},
            "unit":       {"$last": "$unit"},
            "trend":      {"$last": "$trend"},
            "source":     {"$last": "$source"},
            "updated_at": {"$last": "$updated_at"},
            "name":       {"$last": "$name"},
        }},
        {"$sort": {"_id": -1}},
        {"$limit": limit},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0}},
    ]
    result = list(collection.aggregate(pipeline))
    return _serialize(result)

@router.get("/real-time", response_model=List[dict])
async def get_real_time_data(indicator: Optional[str] = None):
    """
    获取实时指标数据，附带涨跌信息。
    - 股票/能源类：与上一个交易日（24h前）的最近一条对比
    - 政治/宏观类：与本指标的上一条记录对比
    """
    collection = db.db["real_time_data"]

    # 取每个指标最新一条
    pipeline = [
        {"$sort": {"updated_at": -1}},
        {"$group": {
            "_id": "$name",
            "name": {"$first": "$name"},
            "value": {"$first": "$value"},
            "unit": {"$first": "$unit"},
            "updated_at": {"$first": "$updated_at"},
            "source": {"$first": "$source"},
        }},
        {"$project": {"_id": 0}},
    ]
    latest_list = list(collection.aggregate(pipeline))

    # 按指标类型决定对比基准的时间窗口
    # 股票/能源：取 20~28h 前的最近一条（上一交易日收盘）
    # 其他：取当前值之前的最近一条（上一次采集）
    MARKET_NAMES = {'标普500', '纳斯达克指数', '道琼斯指数', '波动率指数VIX', '布伦特原油期货', '纽约原油期货', '美元指数', 'RBOB汽油价格', '10年期国债收益率'}

    result = []
    for doc in latest_list:
        name = doc["name"]
        cur_val = doc["value"]
        cur_time = doc["updated_at"]

        if name in MARKET_NAMES:
            # 取 20~28h 前的最近一条
            t_hi = cur_time - timedelta(hours=20)
            t_lo = cur_time - timedelta(hours=28)
            prev = collection.find_one(
                {"name": name, "updated_at": {"$lte": t_hi, "$gte": t_lo}},
                {"value": 1, "updated_at": 1, "_id": 0},
                sort=[("updated_at", -1)]
            )
            # 若 20-28h 窗口无数据，扩大到 48h
            if not prev:
                prev = collection.find_one(
                    {"name": name, "updated_at": {"$lt": cur_time - timedelta(hours=18)}},
                    {"value": 1, "updated_at": 1, "_id": 0},
                    sort=[("updated_at", -1)]
                )
        else:
            # 取当前时间之前的最近一条
            prev = collection.find_one(
                {"name": name, "updated_at": {"$lt": cur_time}},
                {"value": 1, "updated_at": 1, "_id": 0},
                sort=[("updated_at", -1)]
            )

        if prev and prev["value"] is not None and prev["value"] != 0:
            prev_val = prev["value"]
            change = round(cur_val - prev_val, 4)
            change_pct = round((cur_val - prev_val) / abs(prev_val) * 100, 2)
            trend = "up" if change > 0 else ("down" if change < 0 else "stable")
            doc["prev_value"] = prev_val
            doc["prev_time"] = prev["updated_at"]
        else:
            change = None
            change_pct = None
            trend = "unknown"
            doc["prev_value"] = None
            doc["prev_time"] = None

        doc["change"] = change
        doc["change_pct"] = change_pct
        doc["trend"] = trend
        result.append(doc)

    if indicator:
        result = [r for r in result if r["name"] == indicator]

    return _serialize(result)

@router.post("/real-time", response_model=dict)
async def add_real_time_data(data: RealTimeData):
    """
    添加实时指标数据
    """
    collection = db.db["real_time_data"]
    doc = data.model_dump()
    doc["updated_at"] = datetime.utcnow()
    result = collection.insert_one(doc)
    return {"inserted_id": str(result.inserted_id), "status": "success"}

@router.get("/history", response_model=List[DecisionEvent])
async def get_history_data(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    获取历史事件数据
    - **start_time**: 开始时间
    - **end_time**: 结束时间
    - **limit**: 返回数量限制
    """
    collection = db.db["decision_events"]
    query = {}
    if start_time and end_time:
        query["event_time"] = {"$gte": start_time, "$lte": end_time}

    events = []
    for event in collection.find(query).sort("event_time", -1).limit(limit):
        event["_id"] = str(event["_id"])
        events.append(DecisionEvent(**event))
    return events
