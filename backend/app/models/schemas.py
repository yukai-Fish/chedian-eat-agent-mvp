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


class UserLocationHint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    campus: Optional[str] = Field(default=None, max_length=40)
    areaHint: Optional[str] = Field(default=None, max_length=40)
    accuracy: Optional[float] = Field(default=None, ge=0)


class WorkflowRecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="user query")
    uid: Optional[str] = None
    anonymousId: Optional[str] = None
    userId: Optional[str] = None
    chatId: Optional[str] = None
    stream: Optional[bool] = None
    preferNearby: bool = False
    location: Optional[UserLocationHint] = None
    parameters: Optional[dict] = None
    excludeStoreNames: List[str] = Field(default_factory=list, max_length=20)
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
    anonymousId: Optional[str] = None
    userId: Optional[str] = None


class EventAckResponse(BaseModel):
    ok: bool = True


class FavoriteWriteRequest(BaseModel):
    userId: str = Field(..., min_length=1, max_length=120)
    shopId: str = Field(..., min_length=1, max_length=120)
    shopName: Optional[str] = Field(default=None, max_length=120)
    anonymousId: Optional[str] = Field(default=None, max_length=80)
    source: Optional[str] = Field(default="web", max_length=60)


class FavoriteRemoveRequest(BaseModel):
    userId: str = Field(..., min_length=1, max_length=120)
    shopId: str = Field(..., min_length=1, max_length=120)


class FavoriteItem(BaseModel):
    id: int
    user_id: str
    anonymous_id: Optional[str] = None
    shop_id: str
    shop_name: Optional[str] = None
    source: str
    created_at: str


class FavoriteListResponse(BaseModel):
    items: List[FavoriteItem]


class FeedbackRequest(BaseModel):
    feedbackType: str = Field(..., pattern="^(new_store|dining_feedback)$")
    storeName: str = Field(..., min_length=1, max_length=80)
    anonymousId: Optional[str] = Field(default=None, max_length=80)
    userId: Optional[str] = Field(default=None, max_length=80)
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


class StoreReviewItem(BaseModel):
    id: int
    rating: Optional[int] = None
    comment: Optional[str] = None
    recommendDish: Optional[str] = None
    recommendReason: Optional[str] = None
    createdAt: str
    source: Optional[str] = None


class StoreDetailData(BaseModel):
    id: str
    name: str
    campus: str
    area: Optional[str] = None
    avgPrice: int
    openHours: Optional[str] = None
    categoryTags: List[str] = Field(default_factory=list)
    tasteTags: List[str] = Field(default_factory=list)
    sceneTags: List[str] = Field(default_factory=list)
    reviews: List[StoreReviewItem] = Field(default_factory=list)
    reviewCount: int = 0
    avgRating: Optional[float] = None


class StoreDetailResponse(BaseModel):
    found: bool
    store: Optional[StoreDetailData] = None
    message: Optional[str] = None
