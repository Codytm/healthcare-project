"""Admin-only operations. Read routes do not use this router."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.cache import cache_clear
from api.dependencies import require_role
from api.models import TokenData

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Administration"])


@router.post("/cache/clear", summary="Drop cached aggregate responses")
def clear_cache(current_user: TokenData = Depends(require_role("admin"))):
    logger.info("User '%s' cleared the cache", current_user.username)
    try:
        deleted = cache_clear()
    except Exception:
        logger.warning("Cache clear failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )
    return {"deleted": deleted}
