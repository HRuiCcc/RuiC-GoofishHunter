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
    <key>HUNTER_HEADLESS</key><string>true</string>
    <key>HUNTER_QUIET</key><string>1</string>
    <key>HUNTER_DATA_DIR</key><string>$DATA</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <!-- Edge 是 GUI 应用：Background 类型下窗口/渲染进程会被系统限制导致浏览器崩掉，必须 Interactive -->
  <key>ProcessType</key><string>Interactive</string>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
  <key>StandardOutPath</key><string>$DATA/logs/service.log</string>
  <key>StandardErrorPath</key><string>$DATA/logs/service.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

# 等旧 job 真正退出；launchd 在过渡态里会以 EIO(5) 拒绝 bootstrap
for _ in $(seq 1 20); do
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || break
  sleep 0.5
done

# 端口不能有两个实例：先停掉本工程手工启动/遗留的 serve 进程
pkill -f "$ROOT/.venv/bin/python -m hunter serve" 2>/dev/null || true
sleep 1

loaded=false
for _ in $(seq 1 5); do
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
    loaded=true
    break
  fi
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  sleep 1
done
if [ "$loaded" != true ]; then
  echo "launchd 加载失败，请手动执行：launchctl bootstrap gui/$(id -u) $PLIST"
  exit 1
fi
launchctl kickstart -k "gui/$(id -u)/$LABEL"

PORT="${HUNTER_PORT:-7801}"
echo "已安装并启动：$LABEL"
echo "  界面：http://127.0.0.1:$PORT"
echo "  日志：$DATA/logs/service.log"
echo "  卸载：$ROOT/scripts/uninstall_service.sh"
