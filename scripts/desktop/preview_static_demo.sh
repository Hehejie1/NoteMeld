#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' \
    '用法: bash scripts/desktop/preview_static_demo.sh [--port PORT] [--no-open]' \
    '' \
    '选项:' \
    '  --port PORT  指定预览端口（默认 4175）' \
    '  --no-open    不自动打开浏览器' \
    '  --help       显示本帮助'
}

port=4175
open_browser=true

while (($# > 0)); do
  case "$1" in
    --port)
      if (($# < 2)); then
        printf '错误：--port 后必须提供端口。\n' >&2
        exit 2
      fi
      port="$2"
      shift 2
      ;;
    --no-open)
      open_browser=false
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf '错误：未知参数 %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! "$port" =~ ^[0-9]+$ ]] || ((port < 1 || port > 65535)); then
  printf '错误：端口必须是 1 到 65535 之间的整数。\n' >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/../.." && pwd)"
frontend_dir="$repo_dir/desktop/frontend"

if ! command -v pnpm >/dev/null 2>&1; then
  printf '错误：未找到 pnpm，请先安装项目要求的 pnpm 9。\n' >&2
  exit 1
fi

if [[ ! -x "$frontend_dir/node_modules/.bin/vite" ]]; then
  printf '错误：前端依赖尚未安装，请先在 desktop/frontend 目录运行 pnpm install。\n' >&2
  exit 1
fi

cd "$frontend_dir"
printf '正在构建纯静态演示页面…\n'
pnpm build:demo

url="http://127.0.0.1:${port}/new"
printf '静态演示已构建，预览地址：%s\n' "$url"
printf '按 Ctrl-C 停止预览。\n'

if [[ "$open_browser" == true ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  fi
fi

exec pnpm preview:demo --host 127.0.0.1 --port "$port"
