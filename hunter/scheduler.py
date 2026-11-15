"""调度器：每 15 秒看一眼有没有到点的关注，最多同时跑 2 个。"""
from __future__ import annotations

import asyncio
import random
from typing import Optional

from hunter import repo
from hunter.logbus import BUS
from hunter.pipeline import Pipeline


class Scheduler:
    def __init__(self, pipeline: Pipeline, tick_seconds: int = 15, max_parallel: int = 2) -> None:
        self.pipeline = pipeline
        self.tick_seconds = tick_seconds
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._active: set[int] = set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="hunter-scheduler")
        BUS.emit("info", "调度器已启动")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        BUS.emit("info", "调度器已停止")

    async def _loop(self) -> None:
        while self._running:
            try:
                due = [watch for watch in repo.watches_due() if watch.id not in self._active]
                for watch in due:
                    if watch.id is None:
                        continue
                    asyncio.create_task(self._run_one(watch.id, watch.name))
                await asyncio.sleep(self.tick_seconds + random.uniform(0, 3))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                BUS.emit("warn", f"调度器异常：{exc}")
                await asyncio.sleep(30)

    async def _run_one(self, watch_id: int, name: str) -> None:
        self._active.add(watch_id)
        try:
            async with self._semaphore:
                await self.pipeline.run_watch(watch_id, trigger="schedule")
        except Exception as exc:  # noqa: BLE001
            BUS.emit("error", f"「{name}」调度执行失败：{exc}")
        finally:
            self._active.discard(watch_id)
