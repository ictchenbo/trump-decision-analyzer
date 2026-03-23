from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from app.models.trump_statement import TrumpStatement, TrumpStatementCreate, TrumpStatementResponse
from app.core.database import db
from bson.objectid import ObjectId

router = APIRouter(prefix="/trump-statements", tags=["trump-statements"])

@router.get("/", response_model=TrumpStatementResponse)
async def get_trump_statements(
    source: Optional[str] = Query(None, description="按数据源过滤"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    keyword: Optional[str] = Query(None, description="关键词搜索内容")
):
    """
    获取特朗普言行数据列表
    - **source**: 可选参数，按数据源过滤（如Truth Social、福克斯新闻等）
    - **start_time**: 可选参数，开始时间
    - **end_time**: 可选参数，结束时间
    - **limit**: 返回数量限制，默认100，最大1000
    - **offset**: 偏移量，默认0
    - **keyword**: 可选参数，按内容关键词搜索
    """
    collection = db.db["trump_statements"]
    query = {}

    if source:
        query["source"] = source
    if keyword:
        # 对content和translation都进行模糊搜索（支持中英文关键词）
        query["$or"] = [
            {"content": {"$regex": keyword, "$options": "i"}},
            {"translation": {"$regex": keyword, "$options": "i"}}
        ]
    if start_time and end_time:
        query["post_time"] = {"$gte": start_time, "$lte": end_time}
    elif start_time:
        query["post_time"] = {"$gte": start_time}
    elif end_time:
        query["post_time"] = {"$lte": end_time}

    cursor = collection.find(query).sort("post_time", -1).skip(offset).limit(limit)
    statements = []
    for stmt in cursor:
        stmt["_id"] = str(stmt["_id"])
        statements.append(TrumpStatement(**stmt))

    total = collection.count_documents(query)

    return TrumpStatementResponse(
        total=total,
        statements=statements,
        fetch_time=datetime.utcnow()
    )

@router.get("/hawkish-daily", response_model=list[dict])
async def get_hawkish_daily_avg():
    """
    获取从2026-02-28以来每日平均鹰派评分，用于曲线图展示
    """
    collection = db.db["trump_statements"]
    pipeline = [
        # 过滤：有鹰派评分，从2026-02-28开始
        {
            "$match": {
                "hawkish_score": {"$exists": True, "$ne": None},
                "post_time": {"$gte": datetime(2026, 2, 28, 0, 0, 0, tzinfo=timezone.utc)}
            }
        },
        # 按日期分组
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m-%d", "date": "$post_time"}
                },
                "avg_score": {"$avg": "$hawkish_score"},
                "count": {"$sum": 1}
            }
        },
        # 按日期排序
        {
            "$sort": {"_id": 1}
        }
    ]

    result = []
    for item in collection.aggregate(pipeline):
        result.append({
            "date": item["_id"],
            "avg_score": round(item["avg_score"], 2),
            "count": item["count"]
        })

    return result

@router.get("/{statement_id}", response_model=TrumpStatement)
async def get_trump_statement(statement_id: str):
    """
    根据ID获取单条特朗普言行数据
    """
    collection = db.db["trump_statements"]
    stmt = collection.find_one({"_id": ObjectId(statement_id)})
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    stmt["_id"] = str(stmt["_id"])
    return TrumpStatement(**stmt)

@router.post("/", response_model=TrumpStatement)
async def create_trump_statement(statement: TrumpStatementCreate):
    """
    创建新的特朗普言行数据
    """
    collection = db.db["trump_statements"]
    stmt_data = statement.model_dump()
    stmt_data["created_at"] = datetime.utcnow()
    stmt_data["updated_at"] = datetime.utcnow()
    
    result = collection.insert_one(stmt_data)
    created_stmt = collection.find_one({"_id": result.inserted_id})
    created_stmt["_id"] = str(created_stmt["_id"])
    return TrumpStatement(**created_stmt)

@router.post("/batch", response_model=dict)
async def batch_create_trump_statements(statements: List[TrumpStatementCreate]):
    """
    批量创建特朗普言行数据
    """
    collection = db.db["trump_statements"]
    stmt_list = []
    for stmt in statements:
        stmt_data = stmt.model_dump()
        stmt_data["created_at"] = datetime.utcnow()
        stmt_data["updated_at"] = datetime.utcnow()
        stmt_list.append(stmt_data)
    
    result = collection.insert_many(stmt_list)
    return {
        "success": True,
        "inserted_count": len(result.inserted_ids),
        "inserted_ids": [str(id) for id in result.inserted_ids]
    }

@router.delete("/{statement_id}", response_model=dict)
async def delete_trump_statement(statement_id: str):
    """
    删除单条特朗普言行数据
    """
    collection = db.db["trump_statements"]
    result = collection.delete_one({"_id": ObjectId(statement_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Statement not found")
    return {"success": True, "deleted_count": result.deleted_count}
