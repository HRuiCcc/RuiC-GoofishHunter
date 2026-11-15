#!/usr/bin/env bash
# 把闲鱼猎手装成 macOS 后台服务（登录即启动、退出自动拉起、不弹任何窗口）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.ruic.goofishhunter"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$ROOT/.venv/bin/python"
DATA="${HUNTER_DATA_DIR:-$HOME/.ruic-goofish-hunter}"

if [ ! -x "$PY" ]; then
  echo "缺少虚拟环境：$PY，先执行 ./start.sh 安装一次"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$DATA/logs"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>-m</string>
    <string>hunter</string>
    <string>serve</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HUNTER_HEADLESS</key><string>false</string>
    <key>HUNTER_QUIET</key><string>1</string>
    <key>HUNTER_DATA_DIR</key><string>$DATA</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$DATA/logs/service.log</string>
  <key>StandardErrorPath</key><string>$DATA/logs/service.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

PORT="${HUNTER_PORT:-7801}"
echo "已安装并启动：$LABEL"
echo "  界面：http://127.0.0.1:$PORT"
echo "  日志：$DATA/logs/service.log"
echo "  卸载：$ROOT/scripts/uninstall_service.sh"
