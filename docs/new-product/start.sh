#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${NOTEMELD_PREVIEW_PORT:-8765}"

if ! [[ "${PORT}" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "错误：NOTEMELD_PREVIEW_PORT 必须是 1-65535 之间的端口号。" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误：未找到 python3，无法启动静态预览服务器。" >&2
  exit 1
fi

find_listeners() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -t -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true
    return
  fi

  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "${PORT}" 2>/dev/null | tr ' ' '\n' | awk '/^[0-9]+$/ { print }' || true
    return
  fi

  echo "错误：需要 lsof 或 fuser 来清理端口 ${PORT} 上的旧预览进程。" >&2
  exit 1
}

stop_listeners() {
  local pids pid
  pids="$(find_listeners)"
  if [[ -z "${pids}" ]]; then
    return
  fi

  echo "发现端口 ${PORT} 上已有预览进程，正在停止：${pids//$'\n'/ }"
  while read -r pid; do
    [[ -n "${pid}" ]] || continue
    kill -TERM "${pid}" 2>/dev/null || true
  done <<< "${pids}"

  for _ in {1..30}; do
    [[ -z "$(find_listeners)" ]] && return
    sleep 0.1
  done

  pids="$(find_listeners)"
  if [[ -n "${pids}" ]]; then
    echo "旧进程未及时退出，强制停止：${pids//$'\n'/ }"
    while read -r pid; do
      [[ -n "${pid}" ]] || continue
      kill -KILL "${pid}" 2>/dev/null || true
    done <<< "${pids}"
  fi
}

cleanup_current() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" 2>/dev/null; then
    kill -TERM "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}

stop_listeners
trap cleanup_current EXIT INT TERM
echo "NoteMeld 原型预览：http://127.0.0.1:${PORT}/"
echo "预览目录：${SCRIPT_DIR}"
echo "服务 PID：启动中"
echo "按 Ctrl-C 停止服务器。"
python3 -m http.server "${PORT}" --bind 127.0.0.1 --directory "${SCRIPT_DIR}" &
SERVER_PID=$!
echo "服务 PID：${SERVER_PID}"
wait "${SERVER_PID}"
