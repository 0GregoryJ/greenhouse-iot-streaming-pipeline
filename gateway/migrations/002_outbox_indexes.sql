-- Optimize retrieval of undelivered events in insertion order.
CREATE INDEX IF NOT EXISTS idx_sensor_events_pending
ON sensor_events(received_at, event_id)
WHERE kafka_published_at IS NULL;

-- Optimize lookup of old acknowledged events for retention cleanup.
CREATE INDEX IF NOT EXISTS idx_sensor_events_published
ON sensor_events(kafka_published_at)
WHERE kafka_published_at IS NOT NULL;