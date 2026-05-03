#!/usr/bin/env bash
# Run the Trending News Worker Agent
set -euo pipefail

cd "$(dirname "$0")/.."
python3 worker.py --config config.yaml "$@"