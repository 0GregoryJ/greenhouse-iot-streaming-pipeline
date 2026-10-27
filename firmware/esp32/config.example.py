# Wi-Fi network (must be 2.4 GHz compatible)
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# Raspberry Pi's LAN IP address
MQTT_HOST = "YOUR_RASPBERRY_PI_IP"
MQTT_PORT = 1883

# Credentials configured in Mosquitto
MQTT_USERNAME = "YOUR_MQTT_USERNAME"
MQTT_PASSWORD = "YOUR_MQTT_PASSWORD"

MQTT_TOPIC = "greenhouse/telemetry"
MQTT_CLIENT_ID = "greenhouse-esp32-001"

# Sampling configuration
SAMPLE_INTERVAL_SECONDS = 5

# Device identification
GATEWAY_ID = "pi-001"

# Physical sensor identifiers
BME280_SENSOR_ID = "bme280-001"
SOIL_SENSOR_ID = "soil-001"
