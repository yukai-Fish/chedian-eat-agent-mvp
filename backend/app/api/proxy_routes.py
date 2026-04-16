import json
import os

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    StoreDetailResponse,
    StoreNameSuggestionsResponse,
    WorkflowRecommendRequest,
    WorkflowRecommendResponse,
    WorkflowResumeRequest,
    WorkflowUploadFileResponse,
)
from app.services.feedback_repository import save_feedback, suggest_store_names
from app.services.shop_repository import fetch_store_detail_by_name
from app.services.spark_local_recommend_service import ask_spark_local_recommend
from app.services.user_profile import build_iterative_profile
from app.services.usage_events import log_query_event
from app.services.xfyun_workflow_service import ask_workflow, resume_workflow, upload_workflow_file


proxy_router = APIRouter()


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
