from datetime import date, datetime
from typing import Any, Optional

from .config import get_settings
from .i18n import legacy_language, resolve_locale
from .service import KitchenService


def create_app():
    try:
        from fastapi import Body, FastAPI, HTTPException, Query
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
        locale: Optional[str] = None
        language: Optional[str] = "en"
        household_id: str = "default"
        checked_in_at: Optional[datetime] = None
        parsed_items: Optional[list[ParsedItemInput]] = None

    class BaseRequest(BaseModel):
        locale: Optional[str] = None
        language: Optional[str] = "en"
        household_id: str = "default"

    class ExpiryAlertRequest(BaseRequest):
        days_threshold: int = 2

    class InventoryConsumeRequest(BaseRequest):
        item_name: str
        quantity: float
        unit: Optional[str] = None

    class BatchUpdateRequest(BaseRequest):
        name: Optional[str] = None
        quantity: Optional[float] = None
        unit: Optional[str] = None
        expiration_date: Optional[date] = None
        checked_in_at: Optional[datetime] = None
        source_text: Optional[str] = None

    class FallbackSearchRequestBody(BaseRequest):
        preferred_ingredients: Optional[list[str]] = None
        reason: Optional[str] = None

    class RecipeIngredientInput(BaseModel):
        name: str
        quantity: Optional[float] = None
        unit: Optional[str] = None
        optional: bool = False

    class RecipeCreateRequest(BaseRequest):
        recipe_id: Optional[str] = None
        title: Optional[str] = None
        title_translations: dict[str, str]
        tags: list[str] = []
        proficiency: str = "established"
        source_type: str = "personal"
        ingredients: list[RecipeIngredientInput]
        condiments: list[str] = []
        steps: list[dict[str, str]]
        macro_summary: dict[str, str]
        search_hints: list[str] = []

    class ServiceResponse(BaseModel):
        status: str
        locale: str
        language: str
        response_markdown: str
        data: dict[str, Any]

    for model in (
        ParsedItemInput,
        CheckinRequest,
        BaseRequest,
        ExpiryAlertRequest,
        InventoryConsumeRequest,
        BatchUpdateRequest,
        FallbackSearchRequestBody,
        RecipeIngredientInput,
        RecipeCreateRequest,
        ServiceResponse,
    ):
        model.model_rebuild()

    def request_locale(locale: Optional[str], language: Optional[str]) -> str:
        return resolve_locale(locale or language)

    settings = get_settings()
    service = KitchenService(settings)
    app = FastAPI(
        title="Chef Claw",
        version="0.1.0",
        description="Local kitchen assistant service for OpenClaw.",
    )

    @app.get("/health", response_model=ServiceResponse)
    def health() -> dict[str, Any]:
        locale = "en"
        return {
            "status": "ok",
            "locale": locale,
            "language": legacy_language(locale),
            "response_markdown": "- Service is healthy.",
            "data": {
                "database_path": str(settings.database_path),
                "recipes_dir": str(settings.recipes_dir),
            },
        }

    @app.post("/checkin", response_model=ServiceResponse)
    def checkin(request: CheckinRequest = Body(...)) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.checkin(
            text=request.text,
            locale=resolved_locale,
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
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.get("/inventory", response_model=ServiceResponse)
    def inventory(
        locale: Optional[str] = Query(None),
        language: Optional[str] = Query("en"),
        household_id: str = Query("default"),
        category: Optional[str] = Query(None),
        expiring_within_days: Optional[int] = Query(None),
        only_available: bool = Query(True),
    ) -> dict[str, Any]:
        resolved_locale = request_locale(locale, language)
        result = service.get_inventory(
            locale=resolved_locale,
            language=language,
            household_id=household_id,
            category=category,
            expiring_within_days=expiring_within_days,
            only_available=only_available,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.get("/inventory/query", response_model=ServiceResponse)
    def inventory_query(
        question: str = Query(...),
        locale: Optional[str] = Query(None),
        language: Optional[str] = Query("en"),
        household_id: str = Query("default"),
    ) -> dict[str, Any]:
        resolved_locale = request_locale(locale, language)
        result = service.query_inventory(
            question=question,
            locale=resolved_locale,
            language=language,
            household_id=household_id,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/inventory/consume", response_model=ServiceResponse)
    def inventory_consume(request: InventoryConsumeRequest) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        try:
            result = service.consume_inventory(
                item_name=request.item_name,
                quantity=request.quantity,
                unit=request.unit,
                locale=resolved_locale,
                language=request.language,
                household_id=request.household_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.patch("/inventory/batches/{batch_id}", response_model=ServiceResponse)
    def update_inventory_batch(
        batch_id: int,
        request: BatchUpdateRequest,
    ) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        try:
            result = service.update_inventory_batch(
                batch_id=batch_id,
                batch_patch=request.model_dump(exclude_unset=True, exclude={"locale", "language", "household_id"}),
                locale=resolved_locale,
                language=request.language,
                household_id=request.household_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.delete("/inventory/batches/{batch_id}", response_model=ServiceResponse)
    def delete_inventory_batch(
        batch_id: int,
        locale: Optional[str] = Query(None),
        language: Optional[str] = Query("en"),
        household_id: str = Query("default"),
    ) -> dict[str, Any]:
        resolved_locale = request_locale(locale, language)
        try:
            result = service.delete_inventory_batch(
                batch_id=batch_id,
                locale=resolved_locale,
                language=language,
                household_id=household_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/plan/day", response_model=ServiceResponse)
    def day_plan(request: BaseRequest) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.plan_day(
            locale=resolved_locale,
            language=request.language,
            household_id=request.household_id,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/plan/weekend", response_model=ServiceResponse)
    def weekend_plan(request: BaseRequest) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.plan_weekend(
            locale=resolved_locale,
            language=request.language,
            household_id=request.household_id,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/alerts/expiry", response_model=ServiceResponse)
    def expiry_alerts(request: ExpiryAlertRequest) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.expiry_alerts(
            locale=resolved_locale,
            language=request.language,
            household_id=request.household_id,
            days_threshold=request.days_threshold,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/alerts/restock", response_model=ServiceResponse)
    def restock_alerts(request: BaseRequest) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.restock_alerts(
            locale=resolved_locale,
            language=request.language,
            household_id=request.household_id,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/recipes/fallback-search-request", response_model=ServiceResponse)
    def fallback_search_request(
        request: FallbackSearchRequestBody,
    ) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.fallback_search_request(
            locale=resolved_locale,
            language=request.language,
            household_id=request.household_id,
            preferred_ingredients=request.preferred_ingredients,
            reason=request.reason,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.get("/recipes", response_model=ServiceResponse)
    def list_recipes(
        locale: Optional[str] = Query(None),
        language: Optional[str] = Query("en"),
        tag: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
    ) -> dict[str, Any]:
        resolved_locale = request_locale(locale, language)
        result = service.list_recipes(
            locale=resolved_locale,
            language=language,
            tag=tag,
            category=category,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/recipes", response_model=ServiceResponse)
    def create_recipe(request: RecipeCreateRequest) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        payload = request.model_dump()
        payload["ingredients"] = [
            item.model_dump(exclude_none=True) for item in request.ingredients
        ]
        try:
            result = service.create_recipe(
                recipe_payload=payload,
                locale=resolved_locale,
                language=request.language,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    @app.post("/recipes/reload", response_model=ServiceResponse)
    def reload_recipes(request: BaseRequest = Body(...)) -> dict[str, Any]:
        resolved_locale = request_locale(request.locale, request.language)
        result = service.reload_recipes(
            locale=resolved_locale,
            language=request.language,
        )
        return {
            "status": result.status,
            "locale": result.locale,
            "language": result.language,
            "response_markdown": result.response_markdown,
            "data": result.data,
        }

    return app
