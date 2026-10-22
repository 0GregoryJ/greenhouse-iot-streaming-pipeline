
"""
Read-only HTTP API for live greenhouse sensor measurements.

Kafka consumers maintain the Redis materialized view.
This service reads that view without directly accessing Kafka.
"""

import logging
import os
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("greenhouse-api")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=3,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify the serving database is available on startup."""
    redis_client.ping()
    logger.info("Connected to Redis")
    yield
    redis_client.close()


app = FastAPI(
    title="Greenhouse Monitoring API",
    description="Read-only API serving the latest IoT sensor measurements.",
    version="0.1.0",
    lifespan=lifespan,
)

# Restrict browser access to explicitly configured frontend origins.
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Check Redis connectivity, not just API process availability."""
    try:
        redis_client.ping()
        return {"status": "ok"}
    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Redis is unavailable",
        )


@app.get("/api/v1/sensors/latest")
def get_latest_readings():
    """Return the latest known measurement for each sensor and metric."""
    try:
        readings = []
        cursor = 0

        # SCAN avoids blocking Redis like the KEYS command can.
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
