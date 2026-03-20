from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List, Literal

def _utc_isoformat(v: datetime) -> str:
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

class TrumpStatementBase(BaseModel):
    content: str
    source: str
    post_time: Optional[datetime] = None
    url: Optional[str] = None
    likes: Optional[int] = None
    shares: Optional[int] = None
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = None
    sentiment_score: Optional[float] = None
    translation: Optional[str] = None       # 中文翻译（LLM 生成）
    hawkish_score: Optional[int] = None     # 鹰派倾向 0-100（LLM 评分）
    hawkish_level: Optional[int] = None     # 鹰派分级 0-5（结构化评分）
    hawkish_word_count: Optional[int] = None # 鹰派词汇计数（规则法）
    llm_enriched: Optional[bool] = None     # 是否已经过 LLM 增强

class TrumpStatementCreate(TrumpStatementBase):
    pass

class TrumpStatement(TrumpStatementBase):
    id: Optional[str] = Field(None, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: _utc_isoformat
        }
        populate_by_name = True

class TrumpStatementResponse(BaseModel):
    total: int
    statements: List[TrumpStatement]
    fetch_time: datetime
