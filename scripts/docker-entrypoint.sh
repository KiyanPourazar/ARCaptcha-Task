#!/usr/bin/env bash
# Start a shared X display + noVNC so Docker Headful runs are watchable on :7900,
# then launch the platform API. UC Mode Chrome attaches to DISPLAY when headful.
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-99}"
export DISPLAY=":${DISPLAY_NUM}"
export DOCKER_UC_DISPLAY="${DISPLAY}"

SCREEN_GEOM="${SCREEN_WIDTH:-1440}x${SCREEN_HEIGHT:-900}x${SCREEN_DEPTH:-24}"

if [[ ! -e "/tmp/.X${DISPLAY_NUM}-lock" ]]; then
  echo "[entrypoint] starting Xvfb on ${DISPLAY} (${SCREEN_GEOM})"
  Xvfb "${DISPLAY}" -screen 0 "${SCREEN_GEOM}" -ac +extension RANDR +render -noreset &
  # Wait until the lock appears so Chrome does not race the display.
  for _ in $(seq 1 30); do
    [[ -e "/tmp/.X${DISPLAY_NUM}-lock" ]] && break
    sleep 0.2
  done
fi

if ! pgrep -x x11vnc >/dev/null 2>&1; then
  echo "[entrypoint] starting x11vnc on :5900"
  x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -nopw -xkb -bg -o /tmp/x11vnc.log
fi

NOVNC_WEB=""
for candidate in /usr/share/novnc /opt/novnc; do
  if [[ -d "${candidate}" ]] && { [[ -f "${candidate}/vnc.html" ]] || [[ -f "${candidate}/index.html" ]]; }; then
    NOVNC_WEB="${candidate}"
    break
  fi
done
if [[ -z "${NOVNC_WEB}" && -d /usr/share/novnc ]]; then
  NOVNC_WEB=/usr/share/novnc
fi

if [[ -n "${NOVNC_WEB}" ]] && ! pgrep -f "websockify.*7900" >/dev/null 2>&1; then
  echo "[entrypoint] starting noVNC on :7900 (web=${NOVNC_WEB})"
  websockify --web="${NOVNC_WEB}" 7900 localhost:5900 &
fi

echo "[entrypoint] DISPLAY=${DISPLAY} DRIVER_MODE=${DRIVER_MODE:-uc}"
exec "$@"
