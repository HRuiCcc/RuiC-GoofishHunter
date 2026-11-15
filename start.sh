#!/usr/bin/env bash
# 一键启动：装依赖 → 构建前端（首次）→ 起服务
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "==> 创建虚拟环境"
  python3 -m venv .venv
  "$PY" -m pip install -q --upgrade pip
fi

echo "==> 安装后端依赖"
"$PY" -m pip install -q -r requirements.txt

if [ ! -f webui/dist/index.html ]; then
  echo "==> 构建前端（首次）"
  (cd webui && npm install --silent && npm run build)
fi

echo "==> 启动闲鱼猎手 http://127.0.0.1:${HUNTER_PORT:-7801}"
exec "$PY" -m hunter serve "$@"
