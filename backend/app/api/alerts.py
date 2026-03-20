from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import List, Optional
from app.models.alert import Alert
from app.core.database import db
from bson.objectid import ObjectId
from bson.errors import InvalidId

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("/", response_model=List[Alert])
async def get_alerts(
    level: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    获取预警列表
    - **level**: 预警级别过滤（red/yellow/green）
    - **status**: 预警状态过滤（unread/read/dismissed）
    - **limit**: 返回数量限制
    """
    collection = db.db["alerts"]
    query = {}
    if level:
        query["level"] = level
    if status:
        query["status"] = status
    
    alerts = []
    for alert in collection.find(query).sort("alert_time", -1).limit(limit):
        alert["_id"] = str(alert["_id"])
        alerts.append(Alert(**alert))
    return alerts

@router.post("/", response_model=dict)
async def create_alert(alert: Alert):
    """
    创建新的预警
    """
    collection = db.db["alerts"]
    alert_data = alert.model_dump(by_alias=True, exclude={"id"})
    alert_data["alert_time"] = datetime.utcnow()
    result = collection.insert_one(alert_data)
    return {"inserted_id": str(result.inserted_id), "status": "success"}

@router.put("/{alert_id}/status", response_model=dict)
async def update_alert_status(alert_id: str, status: str):
    """
    更新预警状态
    - **status": 新的状态（unread/read/dismissed）
    """
    try:
        oid = ObjectId(alert_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid alert_id format")
    collection = db.db["alerts"]
    result = collection.update_one(
        {"_id": oid},
        {"$set": {"status": status, "updated_at": datetime.utcnow()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "modified_count": result.modified_count}

@router.delete("/{alert_id}", response_model=dict)
async def delete_alert(alert_id: str):
    """
    删除预警
    """
    try:
        oid = ObjectId(alert_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid alert_id format")
    collection = db.db["alerts"]
    result = collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "success", "deleted_count": result.deleted_count}
