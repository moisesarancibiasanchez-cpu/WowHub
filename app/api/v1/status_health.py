"""Health check endpoint público — sin auth."""
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/status", tags=["health"])


@router.get("/health")
async def health_check():
    """Health check público — sin auth requerida."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "wowhub-api"
    }
