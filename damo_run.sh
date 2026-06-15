#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export DAMO_WORKSPACE="${DAMO_WORKSPACE:-$(pwd)}"

previous_day() {
  if date -v-1d +%F >/dev/null 2>&1; then
    date -v-1d +%F
  else
    date -d yesterday +%F
  fi
}

export DAMO_START_DATE="${DAMO_START_DATE:-$(previous_day)}"
export DAMO_END_DATE="${DAMO_END_DATE:-$DAMO_START_DATE}"
export DAMO_WHISPER_MODEL="${DAMO_WHISPER_MODEL:-tiny}"

./scripts/ensure_opencli_bridge.sh || echo "WARN: OpenCLI Browser Bridge unavailable; continuing with API/audio fallbacks." >&2
python3 damo_tracker.py
python3 damo_format_result.py

archive_dir="$DAMO_WORKSPACE/damo_runs"
mkdir -p "$archive_dir"
stamp="$(date +%Y%m%d_%H%M%S)"
range_key="${DAMO_START_DATE}_${DAMO_END_DATE}"
cp damo_result.json "$archive_dir/damo_result_${range_key}_${stamp}.json"
cp damo_report_current.md "$archive_dir/damo_report_${range_key}_${stamp}.md"
