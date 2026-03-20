from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime
from app.core.database import db

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/")
async def get_images(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取特朗普相关图片列表（按采集时间倒序）"""
    col = db.db["trump_images"]
    cursor = col.find({}, {"_id": 0, "url": 1, "title": 1, "source_url": 1, "crawled_at": 1}) \
                .sort("crawled_at", -1) \
                .skip(offset) \
                .limit(limit)
    images = list(cursor)
    total = col.count_documents({})
    return {"total": total, "images": images}
