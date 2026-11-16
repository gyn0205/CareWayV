"""Register the versioned HTTP API routes."""

from fastapi import APIRouter

from app.api.wayfinding import router as wayfinding_router
from app.core.config import settings

api_router = APIRouter(prefix=settings.API_V1_PREFIX)
api_router.include_router(wayfinding_router)
