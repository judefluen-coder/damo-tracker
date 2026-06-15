#!/usr/bin/env bash
set -euo pipefail

ROOT="${DAMO_WORKSPACE:-$(cd "$(dirname "$0")/.." && pwd)}"
PROFILE_DIR="${ROOT}/tmp/opencli-cft-profile"
EXT_DIR="${OPENCLI_EXT_DIR:-${ROOT}/opencli-extension}"
LOG_FILE="/tmp/opencli-cft.log"

bridge_connected() {
  opencli daemon status >/tmp/opencli-status.log 2>&1 || return 1
  grep -qi "Extension: connected" /tmp/opencli-status.log
}

find_browser_app() {
  if [ -n "${OPENCLI_BROWSER_APP:-}" ] && [ -d "${OPENCLI_BROWSER_APP}" ]; then
    printf '%s\n' "${OPENCLI_BROWSER_APP}"
    return 0
  fi
  if [ -d "/Applications/Google Chrome.app" ]; then
    printf '%s\n' "/Applications/Google Chrome.app"
    return 0
  fi
  find "${HOME}/Library/Caches/ms-playwright" -maxdepth 4 -name "Google Chrome for Testing.app" -print -quit 2>/dev/null || true
}

wait_for_bridge() {
  for _ in $(seq 1 "${1:-20}"); do
    if bridge_connected; then
      return 0
    fi
    sleep 2
  done
  return 1
}

if bridge_connected; then
  exit 0
fi

opencli daemon restart >/tmp/opencli-daemon-restart.log 2>&1 || true

BROWSER_APP="$(find_browser_app | head -n 1)"
if [ -z "${BROWSER_APP}" ] || [ ! -d "${BROWSER_APP}" ]; then
  echo "No usable Chrome app found for OpenCLI Browser Bridge" >&2
  cat /tmp/opencli-doctor.log >&2 || true
  exit 1
fi

open -a "${BROWSER_APP}" about:blank >/dev/null 2>&1 || true
if wait_for_bridge 15; then
  exit 0
fi

if [ "${OPENCLI_ALLOW_TEMP_PROFILE:-0}" != "1" ]; then
  echo "OpenCLI Browser Bridge is not connected in the normal Chrome profile." >&2
  echo "Load or reload the OpenCLI extension in chrome://extensions/ for the logged-in Chrome profile." >&2
  opencli daemon status >&2 || true
  opencli doctor >/tmp/opencli-doctor.log 2>&1 || true
  cat /tmp/opencli-doctor.log >&2 || true
  exit 1
fi

mkdir -p "${PROFILE_DIR}"
if [ ! -f "${EXT_DIR}/manifest.json" ]; then
  echo "OpenCLI extension not found: ${EXT_DIR}" >&2
  cat /tmp/opencli-doctor.log >&2 || true
  exit 1
fi

if ! pgrep -f "opencli-cft-profile" >/dev/null 2>&1; then
  rm -f "${PROFILE_DIR}"/SingletonCookie "${PROFILE_DIR}"/SingletonLock "${PROFILE_DIR}"/SingletonSocket
  open -na "${BROWSER_APP}" --args \
    --user-data-dir="${PROFILE_DIR}" \
    --load-extension="${EXT_DIR}" \
    --disable-extensions-except="${EXT_DIR}" \
    --remote-debugging-port=9223 \
    --no-first-run \
    --no-default-browser-check \
    about:blank >/dev/null 2>"${LOG_FILE}" || true
fi

# Chrome for Testing can be alive with no debuggable page target, which leaves
# the OpenCLI extension loaded but disconnected. Ensure one normal tab exists.
if command -v curl >/dev/null 2>&1; then
  if curl -fsS "http://127.0.0.1:9223/json/list" 2>/dev/null | grep -q '^\[\s*\]$'; then
    curl -fsS -X PUT "http://127.0.0.1:9223/json/new?https://www.bilibili.com" >/dev/null 2>&1 || true
  fi
fi

if wait_for_bridge 20; then
  exit 0
fi

opencli daemon status >&2 || true
opencli doctor >/tmp/opencli-doctor.log 2>&1 || true
cat /tmp/opencli-doctor.log >&2 || true
exit 1
