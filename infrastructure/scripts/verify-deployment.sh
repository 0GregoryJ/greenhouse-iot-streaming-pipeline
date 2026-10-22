
#!/usr/bin/env bash
set -Eeuo pipefail

# Verify a deployed component of the greenhouse streaming platform.
#
# Usage:
#   bash infrastructure/scripts/verify-deployment.sh pi
#   bash infrastructure/scripts/verify-deployment.sh kafka
#   bash infrastructure/scripts/verify-deployment.sh backend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

KAFKA_TOPIC="${KAFKA_TOPIC:-greenhouse.sensor-readings}"
KAFKA_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-}"

failures=0

pass() {
  printf 'PASS  %s\n' "$1"
}

fail() {
  printf 'FAIL  %s\n' "$1" >&2
  failures=$((failures + 1))
}

check_service() {
  local name="$1"

  if systemctl is-active --quiet "${name}"; then
    pass "${name} is active"
  else
    fail "${name} is not active"
  fi
}

check_timer() {
  local name="$1"

  if systemctl is-enabled --quiet "${name}" &&
     systemctl is-active --quiet "${name}"; then
    pass "${name} is enabled and active"
  else
    fail "${name} is not enabled and active"
  fi
}

verify_pi() {
  echo "Checking Raspberry Pi gateway..."

  check_service mosquitto
  check_service greenhouse-ingest
  check_service greenhouse-kafka-producer

  check_timer greenhouse-cleanup.timer
  check_timer greenhouse-health.timer

  local health_script="${REPO_ROOT}/gateway/health.py"
  local python_bin="${REPO_ROOT}/.venv/bin/python"

  if [[ -x "${python_bin}" && -f "${health_script}" ]]; then
    # The health script returns 0=healthy, 1=warning, 2=critical.
    local rc=0
    "${python_bin}" "${health_script}" || rc=$?

    case "${rc}" in
      0) pass "Gateway health check: healthy" ;;
      1) echo "WARN  Gateway health check: degraded" ;;
      *) fail "Gateway health check: critical or failed" ;;
    esac
  else
    fail "Gateway health script or Python environment missing"
  fi
}

verify_kafka() {
  echo "Checking Kafka broker..."

  check_service kafka
  check_service tailscaled

  local cli="${HOME}/kafka/bin/kafka-topics.sh"

  if [[ ! -x "${cli}" ]]; then
    fail "Kafka command-line tools not found at ${cli}"
    return
  fi

  if [[ -z "${KAFKA_SERVERS}" ]]; then
    fail "KAFKA_BOOTSTRAP_SERVERS is not set"
    return
  fi

  if "${cli}" \
      --bootstrap-server "${KAFKA_SERVERS}" \
      --list 2>/dev/null | grep -Fxq "${KAFKA_TOPIC}"; then
    pass "Kafka topic ${KAFKA_TOPIC} is available"
  else
    fail "Unable to verify Kafka topic ${KAFKA_TOPIC}"
  fi
}

verify_backend() {
  echo "Checking live backend..."

  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker is not installed"
    return
  fi

  if ! docker compose -f "${REPO_ROOT}/compose.yaml" config \
       --quiet >/dev/null 2>&1; then
    fail "Docker Compose configuration is invalid"
    return
  fi

  pass "Docker Compose configuration is valid"

  for service in redis live-consumer api; do
    local container_id
    container_id="$(
      docker compose -f "${REPO_ROOT}/compose.yaml" \
        ps -q "${service}"
    )"

    if [[ -n "${container_id}" ]] &&
       [[ "$(docker inspect -f '{{.State.Running}}' \
         "${container_id}" 2>/dev/null)" == "true" ]]; then
      pass "Container ${service} is running"
    else
      fail "Container ${service} is not running"
    fi
  done

  if curl --fail --silent --show-error \
      --max-time 5 \
      http://127.0.0.1:8000/health >/dev/null; then
    pass "FastAPI health endpoint responds"
  else
    fail "FastAPI health endpoint failed"
  fi

  if curl --fail --silent --show-error \
      --max-time 5 \
      https://api.gregoryjoshua.com/health >/dev/null; then
    pass "Public HTTPS endpoint responds"
  else
    fail "Public HTTPS endpoint failed"
  fi
}

case "${1:-}" in
  pi)
    verify_pi
    ;;
  kafka)
    verify_kafka
    ;;
  backend)
    verify_backend
    ;;
  *)
    echo "Usage: $0 {pi|kafka|backend}" >&2
    exit 2
    ;;
esac

echo
if [[ "${failures}" -eq 0 ]]; then
  echo "Verification completed without critical failures."
else
  echo "Verification failed: ${failures} issue(s)." >&2
  exit 1
fi
