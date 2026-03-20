from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class Alert(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    alert_time: datetime = Field(default_factory=datetime.utcnow)
    level: str  # red, yellow, green
    title: str
    content: str
    trigger_factors: list[str]
    status: str = "unread"  # unread, read, dismissed
    event_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        populate_by_name = True
