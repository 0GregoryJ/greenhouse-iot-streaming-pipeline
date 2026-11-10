
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from api.services.history import fetch_history

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/history",
    tags=["Historical Analytics"],
)


@router.get("/series")
def get_history_series(
    sensor_id: str = Query(min_length=1, max_length=128),
    measurement_type: str = Query(min_length=1, max_length=128),
    period: Literal["24h", "7d", "30d"] = "7d",
):
    try:
        return fetch_history(
            sensor_id=sensor_id,
            measurement_type=measurement_type,
            period=period,
        )

    except Exception:
        logger.exception("Historical analytics query failed")
        raise HTTPException(
            status_code=503,
            detail="Historical analytics temporarily unavailable",
        )
