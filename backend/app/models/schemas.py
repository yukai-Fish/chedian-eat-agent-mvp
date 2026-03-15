from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="natural language query")
    top_k: int = Field(default=3, ge=1, le=10)


class ParsedSlots(BaseModel):
    budget_max: Optional[int] = None
    location: Optional[str] = None
    scene: Optional[str] = None
    taste: Optional[str] = None
    time: Optional[str] = None


class ShopResult(BaseModel):
    shop_id: str
    name: str
    campus: str
    avg_price: int
    tags: List[str]
    score: float
    reason: str


class RecommendResponse(BaseModel):
    parsed: ParsedSlots
    recommendations: List[ShopResult]
    meta: dict


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    contentType: Literal["text", "image"] = "text"
    content: str


class WorkflowRecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="user query")
    uid: Optional[str] = None
    chatId: Optional[str] = None
    stream: Optional[bool] = None
    parameters: Optional[dict] = None
    history: List[HistoryMessage] = Field(default_factory=list)


class WorkflowRecommendResponse(BaseModel):
    ok: bool
    answer: Optional[str] = None
    raw: Optional[Any] = None
    error: Optional[str] = None
    code: Optional[int] = None
    finishReason: Optional[str] = None


class WorkflowResumeRequest(BaseModel):
    eventId: str = Field(..., min_length=1)
    eventType: Literal["resume", "ignore", "abort"] = "resume"
    content: Optional[str] = None
    stream: Optional[bool] = None


class WorkflowUploadFileResponse(BaseModel):
    ok: bool
    url: Optional[str] = None
    raw: Optional[Any] = None
    error: Optional[str] = None
    code: Optional[int] = None


class HotRankingItem(BaseModel):
    rank: int
    shop_id: str
    name: str
    tag: str
    campus: str
    avg_price: int
    query: str
    trend: str = "flat"  # up | down | flat
    delta: int = 0
    today_count: int = 0
    yesterday_count: int = 0


class HotRankingResponse(BaseModel):
    updated_at: str
    source: str
    items: List[HotRankingItem]


class RankingClickEventRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    shop_name: Optional[str] = None
    uid: Optional[str] = None


class EventAckResponse(BaseModel):
    ok: bool = True


class FeedbackRequest(BaseModel):
    feedbackType: str = Field(..., pattern="^(new_store|dining_feedback)$")
    storeName: str = Field(..., min_length=1, max_length=80)
    area: Optional[str] = Field(default=None, max_length=40)
    category: Optional[str] = Field(default=None, max_length=40)
    avgPrice: Optional[int] = Field(default=None, ge=0, le=500)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    sceneTags: List[str] = Field(default_factory=list)
    tasteTags: List[str] = Field(default_factory=list)
    featureTags: List[str] = Field(default_factory=list)
    recommendDish: Optional[str] = Field(default=None, max_length=80)
    shortIntro: Optional[str] = Field(default=None, max_length=200)
    recommendReason: Optional[str] = Field(default=None, max_length=200)
    comment: Optional[str] = Field(default=None, max_length=500)
    warningNote: Optional[str] = Field(default=None, max_length=200)
    source: Optional[str] = Field(default="frontend_user_feedback", max_length=60)


class FeedbackResponse(BaseModel):
    ok: bool
    id: Optional[int] = None
    message: str


class StoreNameSuggestionsResponse(BaseModel):
    items: List[str]
