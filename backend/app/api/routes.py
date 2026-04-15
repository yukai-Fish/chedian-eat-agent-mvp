from datetime import date

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    EventAckResponse,
    FavoriteListResponse,
    FavoriteRemoveRequest,
    FavoriteWriteRequest,
    HotRankingResponse,
    RankingClickEventRequest,
    RecommendRequest,
    RecommendResponse,
    StoreNameSuggestionsResponse,
    StoreDetailResponse,
)
from app.services.favorites_repository import add_favorite, list_favorites, remove_favorite
from app.services.feedback_repository import save_feedback, suggest_store_names
from app.services.hot_ranking import get_today_hot_rankings
from app.services.parser import parse_query
from app.services.recommender import recommend
from app.services.shop_repository import count_shops, fetch_store_detail_by_name
from app.services.usage_events import log_query_event, log_ranking_click_event


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/filters")
def filters() -> dict:
    return {
        "locations": ["清水河", "沙河"],
        "scenes": ["一个人", "同学聚餐"],
        "tastes": ["辣", "清淡"],
        "times": ["早餐", "午餐", "晚餐", "夜宵"],
    }


@router.get("/rankings/today", response_model=HotRankingResponse)
def rankings_today() -> HotRankingResponse:
    items = get_today_hot_rankings(limit=5)
    return HotRankingResponse(
        updated_at=date.today().isoformat(),
        source="event-analytics",
        items=items,
    )


@router.post("/events/ranking-click", response_model=EventAckResponse)
def ranking_click_event(req: RankingClickEventRequest) -> EventAckResponse:
    log_ranking_click_event(
        shop_id=req.shop_id,
        shop_name=req.shop_name,
        uid=req.uid,
        anonymous_id=req.anonymousId,
        user_id=req.userId,
        source="web-ranking",
    )
    return EventAckResponse(ok=True)


@router.get("/favorites", response_model=FavoriteListResponse)
def get_favorites(user_id: str) -> FavoriteListResponse:
    uid = user_id.strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required.")
    items = list_favorites(user_id=uid)
    return FavoriteListResponse(items=items)


@router.post("/favorites", response_model=EventAckResponse)
def add_favorite_api(req: FavoriteWriteRequest) -> EventAckResponse:
    add_favorite(
        user_id=req.userId.strip(),
        shop_id=req.shopId.strip(),
        shop_name=(req.shopName or "").strip() or None,
        anonymous_id=(req.anonymousId or "").strip() or None,
        source=(req.source or "web").strip() or "web",
    )
    return EventAckResponse(ok=True)


@router.delete("/favorites", response_model=EventAckResponse)
def remove_favorite_api(req: FavoriteRemoveRequest) -> EventAckResponse:
    remove_favorite(user_id=req.userId.strip(), shop_id=req.shopId.strip())
    return EventAckResponse(ok=True)


@router.get("/stores/suggest", response_model=StoreNameSuggestionsResponse)
def store_name_suggestions(keyword: str = "") -> StoreNameSuggestionsResponse:
    if not keyword.strip():
        return StoreNameSuggestionsResponse(items=[])
    return StoreNameSuggestionsResponse(items=suggest_store_names(keyword=keyword.strip(), limit=8))


@router.get("/stores/detail", response_model=StoreDetailResponse)
def store_detail(name: str = "") -> StoreDetailResponse:
    key = name.strip()
    if not key:
        raise HTTPException(status_code=400, detail="name is required.")

    detail = fetch_store_detail_by_name(key)
    if not detail:
        return StoreDetailResponse(found=False, message="未找到该商家详情，请尝试其他候选店名。")
    return StoreDetailResponse(found=True, store=detail)


@router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback(req: FeedbackRequest) -> FeedbackResponse:
    if req.feedbackType == "dining_feedback":
        if req.rating is None:
            raise HTTPException(status_code=400, detail="吃后反馈需要评分（1-5）。")
        if not (req.comment or "").strip():
            raise HTTPException(status_code=400, detail="吃后反馈需要填写评论内容。")

    feedback_id = save_feedback(
        {
            "feedback_type": req.feedbackType,
            "store_name": req.storeName.strip(),
            "anonymous_id": (req.anonymousId or "").strip() or None,
            "user_id": (req.userId or "").strip() or None,
            "area": (req.area or "").strip() or None,
            "category": (req.category or "").strip() or None,
            "avg_price": req.avgPrice,
            "rating": req.rating,
            "scene_tags": ",".join(req.sceneTags) if req.sceneTags else None,
            "taste_tags": ",".join(req.tasteTags) if req.tasteTags else None,
            "feature_tags": ",".join(req.featureTags) if req.featureTags else None,
            "recommend_dish": (req.recommendDish or "").strip() or None,
            "short_intro": (req.shortIntro or "").strip() or None,
            "recommend_reason": (req.recommendReason or "").strip() or None,
            "comment": (req.comment or "").strip() or None,
            "warning_note": (req.warningNote or "").strip() or None,
            "source": (req.source or "frontend_user_feedback").strip() or "frontend_user_feedback",
        }
    )
    return FeedbackResponse(ok=True, id=feedback_id, message="反馈提交成功，感谢你共建成电美食地图。")


@router.post("/recommend", response_model=RecommendResponse)
def recommend_api(req: RecommendRequest) -> RecommendResponse:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    parsed = parse_query(req.query)
    items = recommend(parsed, req.top_k)
    log_query_event(req.query, source="rule-recommend")

    return RecommendResponse(
        parsed=parsed,
        recommendations=items,
        meta={
            "total_candidates": count_shops(),
            "returned": len(items),
            "engine": "rule-based",
        },
    )
