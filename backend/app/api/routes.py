from datetime import date
import os

from fastapi import APIRouter, Header, HTTPException

from app.models.schemas import (
    AdAdminAckResponse,
    AdAdminSlotsResponse,
    AdAdminToggleRequest,
    AdAdminUpsertRequest,
    AdClickEventRequest,
    AdSlotsResponse,
    EventAckResponse,
    FavoriteListResponse,
    FavoriteRemoveRequest,
    FavoriteWriteRequest,
    FeedbackRequest,
    FeedbackResponse,
    HotRankingResponse,
    RankingClickEventRequest,
    RecommendRequest,
    RecommendResponse,
    StoreDetailResponse,
    StoreNameSuggestionsResponse,
)
from app.services.ad_repository import (
    get_ads_contact_wechat,
    list_admin_ad_slots,
    list_public_ad_slots,
    log_ad_click_event,
    set_ad_slot_active,
    set_ads_contact_wechat,
    upsert_ad_slots,
)
from app.services.favorites_repository import add_favorite, list_favorites, remove_favorite
from app.services.feedback_repository import save_feedback, suggest_store_names
from app.services.hot_ranking import get_today_hot_rankings
from app.services.parser import parse_query
from app.services.recommender import recommend
from app.services.shop_repository import count_shops, fetch_store_detail_by_name, resolve_shop_identity_by_name
from app.services.usage_events import log_query_event, log_ranking_click_event


router = APIRouter()


def _require_ads_admin_token(*, header_token: str | None, query_token: str | None) -> None:
    expected = os.getenv("ADS_ADMIN_TOKEN", "").strip()
    if not expected:
        return
    provided = str(header_token or query_token or "").strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid admin token")


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


@router.get("/ads/slots", response_model=AdSlotsResponse)
def ad_slots_public(limit: int = 10) -> AdSlotsResponse:
    slots = list_public_ad_slots(limit=limit)
    return AdSlotsResponse(
        updatedAt=date.today().isoformat(),
        contactWechat=get_ads_contact_wechat(),
        items=slots,
    )


@router.post("/events/ad-click", response_model=EventAckResponse)
def ad_click_event(req: AdClickEventRequest) -> EventAckResponse:
    log_ad_click_event(
        slot_id=req.slotId,
        uid=req.uid,
        anonymous_id=req.anonymousId,
        user_id=req.userId,
        source=(req.source or "miniprogram_ads").strip() or "miniprogram_ads",
    )
    return EventAckResponse(ok=True)


@router.get("/ads/admin/slots", response_model=AdAdminSlotsResponse)
def ad_slots_admin(
    days: int = 30,
    token: str = "",
    x_admin_token: str | None = Header(default=None, alias="x-admin-token"),
) -> AdAdminSlotsResponse:
    _require_ads_admin_token(header_token=x_admin_token, query_token=token)
    items = list_admin_ad_slots(days=days)
    return AdAdminSlotsResponse(
        updatedAt=date.today().isoformat(),
        contactWechat=get_ads_contact_wechat(),
        items=items,
    )


@router.post("/ads/admin/slots", response_model=AdAdminSlotsResponse)
def ad_slots_admin_upsert(
    req: AdAdminUpsertRequest,
    token: str = "",
    x_admin_token: str | None = Header(default=None, alias="x-admin-token"),
) -> AdAdminSlotsResponse:
    _require_ads_admin_token(header_token=x_admin_token, query_token=token)
    if req.contactWechat is not None:
        set_ads_contact_wechat(req.contactWechat)
    if req.slots:
        upsert_ad_slots([item.model_dump() for item in req.slots])
    items = list_admin_ad_slots(days=30)
    return AdAdminSlotsResponse(
        updatedAt=date.today().isoformat(),
        contactWechat=get_ads_contact_wechat(),
        items=items,
    )


@router.post("/ads/admin/toggle", response_model=AdAdminAckResponse)
def ad_slots_admin_toggle(
    req: AdAdminToggleRequest,
    token: str = "",
    x_admin_token: str | None = Header(default=None, alias="x-admin-token"),
) -> AdAdminAckResponse:
    _require_ads_admin_token(header_token=x_admin_token, query_token=token)
    ok = set_ad_slot_active(slot_id=req.slotId, is_active=req.isActive)
    if not ok:
        raise HTTPException(status_code=404, detail="slot not found")
    return AdAdminAckResponse(ok=True, message="slot status updated")


@router.get("/favorites", response_model=FavoriteListResponse)
def get_favorites(user_id: str) -> FavoriteListResponse:
    uid = user_id.strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required.")
    items = list_favorites(user_id=uid)
    return FavoriteListResponse(items=items)


@router.post("/favorites", response_model=EventAckResponse)
def add_favorite_api(req: FavoriteWriteRequest) -> EventAckResponse:
    raw_shop_id = req.shopId.strip()
    raw_shop_name = (req.shopName or "").strip()
    matched = resolve_shop_identity_by_name(raw_shop_name or raw_shop_id)
    final_shop_id = str((matched or {}).get("id") or raw_shop_id).strip()
    final_shop_name = str((matched or {}).get("name") or raw_shop_name or raw_shop_id).strip() or None

    add_favorite(
        user_id=req.userId.strip(),
        shop_id=final_shop_id,
        shop_name=final_shop_name,
        anonymous_id=(req.anonymousId or "").strip() or None,
        source=(req.source or "web").strip() or "web",
    )
    return EventAckResponse(ok=True)


@router.delete("/favorites", response_model=EventAckResponse)
def remove_favorite_api(req: FavoriteRemoveRequest) -> EventAckResponse:
    uid = req.userId.strip()
    raw_shop_id = req.shopId.strip()
    matched = resolve_shop_identity_by_name(raw_shop_id)
    final_shop_id = str((matched or {}).get("id") or raw_shop_id).strip()

    remove_favorite(user_id=uid, shop_id=final_shop_id)
    if final_shop_id != raw_shop_id:
        # Backward compatibility for rows previously saved with plain store names.
        remove_favorite(user_id=uid, shop_id=raw_shop_id)
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
