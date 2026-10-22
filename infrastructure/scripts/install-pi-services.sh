
#!/usr/bin/env bash
set -Eeuo pipefail

# Install systemd units for the Raspberry Pi gateway.
#
# Usage:
#   sudo bash infrastructure/scripts/install-pi-services.sh
#
# Run from a clone of the repository on the Raspberry Pi.
# Existing services are not restarted or enabled automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SOURCE_DIR="${REPO_ROOT}/infrastructure/systemd"
TARGET_DIR="/etc/systemd/system"

UNITS=(
  greenhouse-ingest.service
  greenhouse-kafka-producer.service
  greenhouse-cleanup.service
  greenhouse-cleanup.timer
  greenhouse-health.service
  greenhouse-health.timer
)

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: Run this script with sudo." >&2
  exit 1
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "ERROR: Missing systemd directory: ${SOURCE_DIR}" >&2
  exit 1
fi

# Prevent accidental installation on the Kafka or API EC2 hosts.
if ! id greenhousepi >/dev/null 2>&1; then
  echo "ERROR: Expected Raspberry Pi user 'greenhousepi' not found." >&2
  exit 1
fi

# Validate the source files before changing installed units.
for unit in "${UNITS[@]}"; do
  if [[ ! -f "${SOURCE_DIR}/${unit}" ]]; then
    echo "ERROR: Required file missing: ${unit}" >&2
    exit 1
  fi
done

# Check systemd syntax before installing.
systemd-analyze verify \
  "${UNITS[@]/#/${SOURCE_DIR}/}"

echo "Installing Raspberry Pi systemd units..."

for unit in "${UNITS[@]}"; do
  install -m 0644 \
    "${SOURCE_DIR}/${unit}" \
    "${TARGET_DIR}/${unit}"

  echo "  Installed ${unit}"
done

systemctl daemon-reload

echo
echo "Systemd units installed and reloaded."
echo "Existing services have NOT been restarted."
echo
echo "To enable timers:"
echo "  sudo systemctl enable --now greenhouse-cleanup.timer"
echo "  sudo systemctl enable --now greenhouse-health.timer"
echo
echo "To restart gateway services after reviewing changes:"
echo "  sudo systemctl restart greenhouse-ingest"
echo "  sudo systemctl restart greenhouse-kafka-producer"
