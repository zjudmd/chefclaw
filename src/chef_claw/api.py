from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from .config import get_settings
from .service import KitchenService


def create_app():
    try:
        from fastapi import FastAPI, Query
        from pydantic import BaseModel, Field
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "FastAPI dependencies are missing. Install with `pip install -e .[dev]`."
        ) from exc

    class ParsedItemInput(BaseModel):
        name: str
        quantity: Optional[float] = None
        unit: Optional[str] = None
        expiration_date: Optional[date] = None

    class CheckinRequest(BaseModel):
        text: str = Field(..., description="Normalized ingredient check-in text.")
        language: str = "en"
        household_id: str = "default"
        checked_in_at: Optional[datetime] = None
        parsed_items: Optional[list[ParsedItemInput]] = None

    class BaseRequest(BaseModel):
        language: str = "en"
        household_id: str = "default"

    class ExpiryAlertRequest(BaseRequest):
        days_threshold: int = 2

    class FallbackSearchRequestBody(BaseRequest):
        preferred_ingredients: Optional[list[str]] = None
        reason: str = "Local recipes are insufficient."

    class ServiceResponse(BaseModel):
        status: str
        language: str
        response_markdown: str
        data: dict[str, Any]

    settings = get_settings()
    service = KitchenService(settings)
    app = FastAPI(
        title="Chef Claw",
        version="0.1.0",
        description="Local kitchen assistant service for OpenClaw.",
    )

    @app.get("/health", response_model=ServiceResponse)
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "language": "en",
            "response_markdown": "- Service is healthy.",
            "data": {
                "database_path": str(settings.database_path),
                "recipes_dir": str(settings.recipes_dir),
            },
        }

    @app.post("/checkin", response_model=ServiceResponse)
    def checkin(request: CheckinRequest) -> dict[str, Any]:
        result = service.checkin(
            text=request.text,
            language=request.language,
            household_id=request.household_id,
            checked_in_at=request.checked_in_at,
            parsed_items=[
                item.model_dump(exclude_none=True)
                for item in request.parsed_items or []
            ]
            or None,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.get("/inventory", response_model=ServiceResponse)
    def inventory(
        language: str = Query("en"),
        household_id: str = Query("default"),
        category: Optional[str] = Query(None),
        expiring_within_days: Optional[int] = Query(None),
        only_available: bool = Query(True),
    ) -> dict[str, Any]:
        result = service.get_inventory(
            language=language,
            household_id=household_id,
            category=category,
            expiring_within_days=expiring_within_days,
            only_available=only_available,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.get("/inventory/query", response_model=ServiceResponse)
    def inventory_query(
        question: str = Query(...),
        language: str = Query("en"),
        household_id: str = Query("default"),
    ) -> dict[str, Any]:
        result = service.query_inventory(
            question=question,
            language=language,
            household_id=household_id,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/plan/day", response_model=ServiceResponse)
    def day_plan(request: BaseRequest) -> dict[str, Any]:
        result = service.plan_day(
            language=request.language,
            household_id=request.household_id,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/plan/weekend", response_model=ServiceResponse)
    def weekend_plan(request: BaseRequest) -> dict[str, Any]:
        result = service.plan_weekend(
            language=request.language,
            household_id=request.household_id,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/alerts/expiry", response_model=ServiceResponse)
    def expiry_alerts(request: ExpiryAlertRequest) -> dict[str, Any]:
        result = service.expiry_alerts(
            language=request.language,
            household_id=request.household_id,
            days_threshold=request.days_threshold,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/alerts/restock", response_model=ServiceResponse)
    def restock_alerts(request: BaseRequest) -> dict[str, Any]:
        result = service.restock_alerts(
            language=request.language,
            household_id=request.household_id,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/recipes/fallback-search-request", response_model=ServiceResponse)
    def fallback_search_request(
        request: FallbackSearchRequestBody,
    ) -> dict[str, Any]:
        result = service.fallback_search_request(
            language=request.language,
            household_id=request.household_id,
            preferred_ingredients=request.preferred_ingredients,
            reason=request.reason,
        )
        return {
            "status": result.status,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    return app
