"""
Read-only HTTP API for greenhouse sensor measurements.

Live data:
    Kafka -> Redis -> FastAPI

Historical data:
    Kafka -> S3 -> Snowflake -> FastAPI

The API serves both live and historical measurements without
directly consuming Kafka events.
"""

import logging
import os
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.routes.history import router as history_router


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("greenhouse-api")


# ---------------------------------------------------------------------
# Redis connection
# ---------------------------------------------------------------------

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
)


# ---------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Verify Redis is available when the API starts.

    Historical Snowflake connections are opened on demand
    by the repository layer, not during application startup.
    """
    redis_client.ping()
    logger.info("Connected to Redis")

    try:
        yield
    finally:
        redis_client.close()
        logger.info("Redis connection closed")


# ---------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------

app = FastAPI(
    title="Greenhouse Monitoring API",
    description=(
        "Read-only API serving live greenhouse sensor measurements "
        "from Redis and historical analytics from Snowflake."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------

app.include_router(history_router)


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.get("/health")
def health():
    """
    Verify Redis connectivity, not just API process availability.

    Snowflake is not included in this health check because
    historical queries are performed on demand.
    """
    try:
        redis_client.ping()
        return {"status": "ok"}

    except redis.RedisError:
        logger.exception("Redis health check failed")
        raise HTTPException(
            status_code=503,
            detail="Redis is unavailable",
        )


# ---------------------------------------------------------------------
# Live sensor measurements
# ---------------------------------------------------------------------

@app.get("/api/v1/sensors/latest")
def get_latest_readings():
    """
    Return the latest known measurement for each sensor and metric.

    The live Kafka consumer maintains these readings in Redis.
    """
    try:
        readings = []
        cursor = 0

        # SCAN avoids blocking Redis like KEYS can.
        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor,
                match="greenhouse:latest:*",
                count=100,
            )

            if keys:
                pipeline = redis_client.pipeline(transaction=False)

                for key in keys:
                    pipeline.hgetall(key)

                results = pipeline.execute()

                for record in results:
                    if not record:
                        continue

                    readings.append({
                        "gateway_id": record.get("gateway_id"),
                        "sensor_id": record.get("sensor_id"),
                        "measurement_type": record.get("measurement_type"),
                        "value": float(record["value"]),
                        "unit": record.get("unit"),
                        "timestamp": record.get("timestamp"),
                        "event_id": record.get("event_id"),
                    })

            if cursor == 0:
                break

        readings.sort(
            key=lambda reading: (
                reading["gateway_id"] or "",
                reading["sensor_id"] or "",
                reading["measurement_type"] or "",
            )
        )

        return {
            "count": len(readings),
            "readings": readings,
        }

    except (redis.RedisError, ValueError, KeyError):
        logger.exception("Unable to retrieve latest readings")
        raise HTTPException(
            status_code=503,
            detail="Sensor readings are temporarily unavailable",
        )
