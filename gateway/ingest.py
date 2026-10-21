#---
# Subscribes to the greenhouse/telemetry MQTT topic,
# validates incoming events against the JSON schema,
# and inserts valid, non-duplicate events into SQLite.
#
# Initializes the database and table if they don't exist.
# Provides a persistent buffer between MQTT ingestion
# and the downstream Kafka producer.
#---
