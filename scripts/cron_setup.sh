#!/usr/bin/env bash
# Set up a cron job for the Trending News Worker Agent
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="${PROJECT_DIR}/.venv"

echo "Trending News Worker Agent - Cron Setup"
echo "========================================"
echo ""
echo "Project directory: ${PROJECT_DIR}"
echo ""

# Create venv if it doesn't exist
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
    echo "Installing dependencies..."
    "${VENV_DIR}/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"
else
    echo "Virtual environment already exists at ${VENV_DIR}"
fi

# Prompt for cron interval
echo ""
echo "Recommended cron intervals:"
echo "  */30 * * * *   - Every 30 minutes"
echo "  0 * * * *      - Every hour"
echo "  0 */2 * * *    - Every 2 hours"
echo ""

read -rp "Enter cron schedule (default: '*/30 * * * *'): " SCHEDULE
SCHEDULE="${SCHEDULE:-*/30 * * * *}"

PYTHON_PATH="${VENV_DIR}/bin/python"
CRON_CMD="cd ${PROJECT_DIR} && ${PYTHON_PATH} worker.py --config config.yaml >> ${PROJECT_DIR}/logs/cron.log 2>&1"

echo ""
echo "Adding cron job:"
echo "${SCHEDULE} ${CRON_CMD}"
echo ""

# Add to crontab
(crontab -l 2>/dev/null; echo "${SCHEDULE} ${CRON_CMD}") | crontab -

echo "Cron job added successfully!"
echo "View crontab with: crontab -l"
echo "Remove with: crontab -l | grep -v 'trending_news_worker' | crontab -"