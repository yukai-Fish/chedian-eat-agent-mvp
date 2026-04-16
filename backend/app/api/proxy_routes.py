import json
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    ProfileDataResponse,
    ProfileSyncRequest,
    StoreDetailResponse,
    StoreNameSuggestionsResponse,
    WechatLoginRequest,
    WechatLoginResponse,
    WorkflowRecommendRequest,
    WorkflowRecommendResponse,
    WorkflowResumeRequest,
    WorkflowUploadFileResponse,
)
from app.services.favorites_repository import add_favorite, list_favorites
from app.services.feedback_repository import save_feedback, suggest_store_names
from app.services.shop_repository import fetch_store_detail_by_name, resolve_shop_identity_by_name
from app.services.spark_local_recommend_service import ask_spark_local_recommend
from app.services.user_profile import build_iterative_profile
from app.services.usage_events import bind_anonymous_events_to_user, list_recent_query_history, log_query_event
from app.services.wechat_auth_service import login_with_wechat_code
from app.services.xfyun_workflow_service import ask_workflow, resume_workflow, upload_workflow_file


proxy_router = APIRouter()


def _clean_text_list(values: list[str], *, limit: int, max_length: int) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if len(text) > max_length:
            text = text[:max_length]
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _favorite_names_for_user(user_id: str, *, limit: int = 100) -> list[str]:
    items = list_favorites(user_id=user_id, limit=limit)
    names: list[str] = []
    seen: set[str] = set()
    for row in items:
        name = str(row.get("shop_name") or row.get("shop_id") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


@proxy_router.post("/recommend", response_model=WorkflowRecommendResponse)
def recommend_via_workflow(req: WorkflowRecommendRequest) -> WorkflowRecommendResponse:
    resolved_uid = req.uid or req.userId or req.anonymousId
    provider = os.getenv("RECOMMEND_PROVIDER", "workflow").strip().lower()
    excluded_names = [str(name).strip() for name in (req.excludeStoreNames or []) if str(name).strip()][:20]
    nearby_context = None
    if req.preferNearby and req.location is not None:
        nearby_context = {
            "preferNearby": True,
            "latitude": req.location.latitude,
            "longitude": req.location.longitude,
            "campus": (req.location.campus or "").strip() or None,
            "areaHint": (req.location.areaHint or "").strip() or None,
            "accuracy": req.location.accuracy,
        }
    profile = build_iterative_profile(
        uid=req.uid,
        anonymous_id=req.anonymousId,
        user_id=req.userId,
    )

    log_query_event(
        req.query,
        uid=resolved_uid,
        anonymous_id=req.anonymousId,
        user_id=req.userId,
        source=f"{provider}-recommend",
        meta={
            "profile_applied": profile.get("hasProfile", False),
            "profile_stats": profile.get("stats", {}),
        },
    )

    if provider == "workflow":
        merged_parameters = dict(req.parameters or {})
        if profile.get("hasProfile"):
            merged_parameters["AGENT_USER_PROFILE_SUMMARY"] = profile.get("summary")
            merged_parameters["AGENT_USER_PROFILE_JSON"] = json.dumps(profile.get("signals", {}), ensure_ascii=False)
        if excluded_names:
            merged_parameters["AGENT_EXCLUDED_STORE_NAMES"] = json.dumps(excluded_names, ensure_ascii=False)
        if nearby_context:
            merged_parameters["AGENT_NEARBY_FIRST"] = "true"
            merged_parameters["AGENT_USER_LOCATION_JSON"] = json.dumps(nearby_context, ensure_ascii=False)

        result = ask_workflow(
            query=req.query,
            uid=resolved_uid,
            chat_id=req.chatId,
            stream=req.stream,
            parameters=merged_parameters,
            history=[item.model_dump() for item in req.history],
        )
        return WorkflowRecommendResponse(**result)

    result = ask_spark_local_recommend(
        query=req.query,
        uid=resolved_uid,
        user_profile=profile if profile.get("hasProfile") else None,
        exclude_store_names=excluded_names,
        nearby_context=nearby_context,
    )
    return WorkflowRecommendResponse(**result)


@proxy_router.post("/auth/wechat-login", response_model=WechatLoginResponse)
def wechat_login_proxy(req: WechatLoginRequest) -> WechatLoginResponse:
    result = login_with_wechat_code(
        code=req.code,
        anonymous_id=req.anonymousId,
    )
    return WechatLoginResponse(**result)


@proxy_router.get("/profile/data", response_model=ProfileDataResponse)
def profile_data_proxy(user_id: str = "") -> ProfileDataResponse:
    uid = user_id.strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required.")
    return ProfileDataResponse(
        ok=True,
        favorites=_favorite_names_for_user(uid, limit=100),
        queryHistory=list_recent_query_history(user_id=uid, limit=20),
    )


@proxy_router.post("/profile/sync-local", response_model=ProfileDataResponse)
def profile_sync_local_proxy(req: ProfileSyncRequest) -> ProfileDataResponse:
    uid = req.userId.strip()
    anon = (req.anonymousId or "").strip() or None
    source = (req.source or "miniprogram").strip() or "miniprogram"

    normalized_favorites = _clean_text_list(req.favorites, limit=80, max_length=120)
    normalized_history = _clean_text_list(req.queryHistory, limit=80, max_length=300)

    linked_count = bind_anonymous_events_to_user(anonymous_id=anon or "", user_id=uid) if anon else 0

    migrated_favorites = 0
    for name in normalized_favorites:
        matched = resolve_shop_identity_by_name(name)
        shop_id = str((matched or {}).get("id") or name).strip()
        shop_name = str((matched or {}).get("name") or name).strip()
        if not shop_id:
            continue
        add_favorite(
            user_id=uid,
            shop_id=shop_id,
            shop_name=shop_name or None,
            anonymous_id=anon,
            source=f"{source}-sync",
        )
        migrated_favorites += 1

    existing_history = set(list_recent_query_history(user_id=uid, limit=200))
    migrated_history = 0
    for query in normalized_history:
        if query in existing_history:
            continue
        log_query_event(
            query,
            uid=uid,
            anonymous_id=anon,
            user_id=uid,
            source=f"{source}-sync",
            meta={"profile_sync": True},
        )
        existing_history.add(query)
        migrated_history += 1

    return ProfileDataResponse(
        ok=True,
        favorites=_favorite_names_for_user(uid, limit=100),
        queryHistory=list_recent_query_history(user_id=uid, limit=20),
        migratedFavorites=migrated_favorites,
        migratedHistory=migrated_history,
        linkedHistoryEvents=linked_count,
    )


@proxy_router.post("/recommend/resume", response_model=WorkflowRecommendResponse)
def resume_workflow_proxy(req: WorkflowResumeRequest) -> WorkflowRecommendResponse:
    workflow_result = resume_workflow(
        event_id=req.eventId,
        event_type=req.eventType,
        content=req.content,
        stream=req.stream,
    )
    return WorkflowRecommendResponse(**workflow_result)


@proxy_router.post("/workflow/upload-file", response_model=WorkflowUploadFileResponse)
async def upload_workflow_file_proxy(file: UploadFile = File(...)) -> WorkflowUploadFileResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="file is empty.")
    result = upload_workflow_file(
        file_name=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type or "application/octet-stream",
    )
    return WorkflowUploadFileResponse(**result)


@proxy_router.get("/stores/suggest", response_model=StoreNameSuggestionsResponse)
def store_name_suggestions_proxy(keyword: str = "") -> StoreNameSuggestionsResponse:
    if not keyword.strip():
        return StoreNameSuggestionsResponse(items=[])
    return StoreNameSuggestionsResponse(items=suggest_store_names(keyword=keyword.strip(), limit=8))


@proxy_router.get("/stores/detail", response_model=StoreDetailResponse)
def store_detail_proxy(name: str = "") -> StoreDetailResponse:
    key = name.strip()
    if not key:
        raise HTTPException(status_code=400, detail="name is required.")

    detail = fetch_store_detail_by_name(key)
    if not detail:
        return StoreDetailResponse(found=False, message="store detail not found.")
    return StoreDetailResponse(found=True, store=detail)


@proxy_router.post("/feedback", response_model=FeedbackResponse)
def submit_feedback_proxy(req: FeedbackRequest) -> FeedbackResponse:
    if req.feedbackType == "dining_feedback":
        if req.rating is None:
            raise HTTPException(status_code=400, detail="rating is required for dining feedback.")
        if not (req.comment or "").strip():
            raise HTTPException(status_code=400, detail="comment is required for dining feedback.")

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
    return FeedbackResponse(ok=True, id=feedback_id, message="feedback submitted successfully.")
