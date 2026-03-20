from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List

def _utc_isoformat(v: datetime) -> str:
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

class RealTimeData(BaseModel):
    name: str
    value: float
    unit: str
    trend: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class FactorScore(BaseModel):
    geopolitical: float
    domestic_political: float
    financial_market: float
    energy_market: float
    decision_team: float

class DecisionEvent(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    title: str
    event_time: datetime
    event_type: str
    composite_index: float
    factor_scores: FactorScore
    description: Optional[str] = None
    source: Optional[List[str]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: _utc_isoformat
        }
        populate_by_name = True
