#!/usr/bin/env bash
# 停掉并移除后台服务
set -euo pipefail
LABEL="com.ruic.goofishhunter"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "已卸载 $LABEL"
