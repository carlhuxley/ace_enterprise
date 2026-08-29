"""REST endpoints for submitting and querying human evaluation feedback.

Bead: ace_enterprise-e98

Mount via:
    from src.api.routes.feedback_routes import create_feedback_router
    app.include_router(create_feedback_router(collector), prefix="/feedback")
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.broker.feedback import FeedbackCollector, HumanFeedback

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class SubmitFeedbackRequest(BaseModel):
    evaluation_id: str
    rating: int = Field(..., ge=1, le=5, description="Quality rating 1 (poor) to 5 (excellent)")
    provider_id: str
    provider_role: str = Field(
        ...,
        description="Role of the feedback provider: developer | reviewer | expert | manager",
    )
    comment: str | None = None

    @field_validator("provider_role")
    @classmethod
    def role_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("provider_role must not be blank")
        return v


class FeedbackResponse(BaseModel):
    evaluation_id: str
    rating: int
    provider_id: str
    provider_role: str
    comment: str | None
    timestamp: datetime


class FeedbackListResponse(BaseModel):
    evaluation_id: str
    feedbacks: list[FeedbackResponse]
    aggregated_rating: float | None


class DriftResponse(BaseModel):
    evaluation_id: str
    automated_score: float
    drift: float
    blended_score: float


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_feedback_router(collector: FeedbackCollector) -> APIRouter:
    """Return an APIRouter wired to the given FeedbackCollector."""

    router = APIRouter(tags=["feedback"])

    def _to_response(fb: HumanFeedback) -> FeedbackResponse:
        return FeedbackResponse(
            evaluation_id=fb.evaluation_id,
            rating=fb.rating,
            provider_id=fb.provider_id,
            provider_role=fb.provider_role,
            comment=fb.comment,
            timestamp=fb.timestamp,
        )

    @router.post(
        "/",
        response_model=FeedbackResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Submit human feedback for an evaluation",
    )
    def submit_feedback(body: SubmitFeedbackRequest) -> FeedbackResponse:
        fb = collector.submit(
            evaluation_id=body.evaluation_id,
            rating=body.rating,
            provider_id=body.provider_id,
            provider_role=body.provider_role,
            comment=body.comment,
        )
        return _to_response(fb)

    @router.get(
        "/{evaluation_id}",
        response_model=FeedbackListResponse,
        summary="Get all feedback for an evaluation",
    )
    def get_feedback(evaluation_id: str) -> FeedbackListResponse:
        feedbacks = collector.get_feedback(evaluation_id)
        return FeedbackListResponse(
            evaluation_id=evaluation_id,
            feedbacks=[_to_response(fb) for fb in feedbacks],
            aggregated_rating=collector.aggregated_rating(evaluation_id),
        )

    @router.get(
        "/{evaluation_id}/drift",
        response_model=DriftResponse,
        summary="Calculate drift between automated and human scores",
    )
    def get_drift(evaluation_id: str, automated_score: float = 0.0) -> DriftResponse:
        if automated_score < 0 or automated_score > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="automated_score must be in [0, 100]",
            )
        now = datetime.now(UTC)
        drift = collector.detect_drift(automated_score, evaluation_id, now=now)
        blended = collector.blended_score(automated_score, evaluation_id, now=now)
        return DriftResponse(
            evaluation_id=evaluation_id,
            automated_score=automated_score,
            drift=drift,
            blended_score=blended,
        )

    return router
