from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    StoreNameSuggestionsResponse,
    WorkflowRecommendRequest,
    WorkflowRecommendResponse,
    WorkflowResumeRequest,
    WorkflowUploadFileResponse,
)
from app.services.feedback_repository import save_feedback, suggest_store_names
from app.services.usage_events import log_query_event
from app.services.xfyun_workflow_service import ask_workflow, resume_workflow, upload_workflow_file


proxy_router = APIRouter()


@proxy_router.post("/recommend", response_model=WorkflowRecommendResponse)
def recommend_via_workflow(req: WorkflowRecommendRequest) -> WorkflowRecommendResponse:
    log_query_event(req.query, uid=req.uid, source="workflow-recommend")
    workflow_result = ask_workflow(
        query=req.query,
        uid=req.uid,
        chat_id=req.chatId,
        stream=req.stream,
        history=[item.model_dump() for item in req.history],
    )
    return WorkflowRecommendResponse(**workflow_result)


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
