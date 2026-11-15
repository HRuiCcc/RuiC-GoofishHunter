"""进程内事件总线：运行日志既要写文件，也要实时推到网页。"""
from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from hunter.config import PATHS


class LogBus:
    def __init__(self, capacity: int = 800) -> None:
        self._events: deque[dict] = deque(maxlen=capacity)
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    def emit(self, level: str, message: str, **fields: Any) -> dict:
        event = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "msg": message,
            **fields,
        }
        self._events.append(event)
        if os.getenv("HUNTER_QUIET", "") != "1":
            print(f"[{event['ts']}] {level.upper():<5} {message}")
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        self._write(event)
        return event

    def _write(self, event: dict) -> None:
        try:
            PATHS.ensure()
            day = datetime.now().strftime("%Y-%m-%d")
            with (PATHS.logs / f"{day}.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def recent(self, limit: int = 200) -> list[dict]:
        return list(self._events)[-limit:]

    async def subscribe(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        try:
            for event in list(self._events)[-50:]:
                queue.put_nowait(event)
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


BUS = LogBus()
