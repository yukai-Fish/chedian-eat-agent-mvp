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


class AdSlotPublicItem(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    scene: str = ""
    audience: str = ""
    priceLabel: str = ""
    imageUrl: str = ""
    landingType: Literal["none", "store_detail", "miniprogram_path", "external_web", "copy_wechat"] = "none"
    landingValue: str = ""
    rank: int = 0


class AdSlotsResponse(BaseModel):
    updatedAt: str
    contactWechat: str
    items: List[AdSlotPublicItem] = Field(default_factory=list)


class AdClickEventRequest(BaseModel):
    slotId: str = Field(..., min_length=1, max_length=80)
    uid: Optional[str] = None
    anonymousId: Optional[str] = None
    userId: Optional[str] = None
    source: Optional[str] = Field(default="miniprogram_ads", max_length=60)


class AdAdminSlotItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=80)
    subtitle: Optional[str] = Field(default="", max_length=180)
    scene: Optional[str] = Field(default="", max_length=80)
    audience: Optional[str] = Field(default="", max_length=180)
    priceLabel: Optional[str] = Field(default="", max_length=40)
    imageUrl: Optional[str] = Field(default="", max_length=1000)
    landingType: Literal["none", "store_detail", "miniprogram_path", "external_web", "copy_wechat"] = "none"
    landingValue: Optional[str] = Field(default="", max_length=500)
    rank: int = 0
    isActive: bool = True
    startsAt: Optional[str] = Field(default="")
    endsAt: Optional[str] = Field(default="")
    updatedAt: Optional[str] = None
    totalClicks: int = 0
    recentClicks: int = 0


class AdAdminSlotsResponse(BaseModel):
    updatedAt: str
    contactWechat: str
    items: List[AdAdminSlotItem] = Field(default_factory=list)


class AdAdminUpsertRequest(BaseModel):
    contactWechat: Optional[str] = Field(default=None, max_length=80)
    slots: List[AdAdminSlotItem] = Field(default_factory=list, max_length=100)


class AdAdminToggleRequest(BaseModel):
    slotId: str = Field(..., min_length=1, max_length=80)
    isActive: bool


class AdAdminAckResponse(BaseModel):
    ok: bool = True
    message: Optional[str] = None


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


class ProfileSyncRequest(BaseModel):
    userId: str = Field(..., min_length=1, max_length=120)
    anonymousId: Optional[str] = Field(default=None, max_length=80)
    favorites: List[str] = Field(default_factory=list, max_length=100)
    queryHistory: List[str] = Field(default_factory=list, max_length=100)
    source: Optional[str] = Field(default="miniprogram", max_length=60)


class ProfileDataResponse(BaseModel):
    ok: bool = True
    favorites: List[str] = Field(default_factory=list)
    queryHistory: List[str] = Field(default_factory=list)
    migratedFavorites: int = 0
    migratedHistory: int = 0
    linkedHistoryEvents: int = 0


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


class StoreBusinessStatus(BaseModel):
    code: Literal["open", "closing", "closed", "unknown"] = "unknown"
    label: str
    detail: str
    evaluatedAt: str


class StoreDetailData(BaseModel):
    id: str
    name: str
    campus: str
    area: Optional[str] = None
    poiId: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None
    geoSource: Optional[str] = None
    phone: Optional[str] = None
    avgPrice: int
    avgPriceMin: int
    avgPriceMax: int
    openHours: Optional[str] = None
    businessStatus: Optional[StoreBusinessStatus] = None
    imageUrls: List[str] = Field(default_factory=list)
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


class WechatLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=200)
    anonymousId: Optional[str] = Field(default=None, max_length=80)


class WechatLoginResponse(BaseModel):
    ok: bool
    provider: str = "wechat_miniprogram"
    userId: Optional[str] = None
    anonymousId: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
