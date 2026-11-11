from fastapi import APIRouter
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.chat import router as chat_router
from backend.app.api.routes.schema import router as schema_router
from backend.app.api.routes.schedules import router as schedules_router
from backend.app.api.routes.auth import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(schema_router)
api_router.include_router(schedules_router)
api_router.include_router(auth_router)
