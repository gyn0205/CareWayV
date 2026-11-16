from fastapi import FastAPI

from app.api import api_router
from app.core.config import settings
from app.core.errors import api_exception_handlers

app = FastAPI(
    title=settings.PROJECT_NAME,
    exception_handlers=api_exception_handlers,
)
app.include_router(api_router)
