"""运行配置：路径、端口、浏览器通道、默认值。

所有可变配置都可以被数据库里的 settings 表覆盖（见 hunter/settings.py），
这里的只负责「进程级」的东西。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Paths:
    data: Path
    db: Path
    profiles: Path
    states: Path
    logs: Path
    shots: Path

    @classmethod
    def resolve(cls) -> "Paths":
        base = Path(os.getenv("HUNTER_DATA_DIR", "~/.ruic-goofish-hunter")).expanduser()
        return cls(
            data=base,
            db=Path(os.getenv("HUNTER_DB", base / "hunter.db")).expanduser(),
            profiles=base / "profiles",
            states=base / "states",
            logs=base / "logs",
            shots=base / "shots",
        )

    def ensure(self) -> None:
        for path in (self.data, self.profiles, self.states, self.logs, self.shots):
            path.mkdir(parents=True, exist_ok=True)


PATHS = Paths.resolve()


@dataclass(frozen=True)
class Runtime:
    host: str
    port: int
    headless: bool
    browser_channel: str
    # 每次 mtop 调用之间的最小间隔（秒），用于自保，不是给别人看的
    call_interval: float
    # 详情请求并发数
    detail_concurrency: int
    # 默认关注间隔
    default_interval_sec: int
    # 详情缓存有效期
    detail_ttl_hours: int
    # 代理：留空 = 直连（绕过系统代理）
    proxy: str

    @classmethod
    def load(cls) -> "Runtime":
        channel = os.getenv("HUNTER_BROWSER_CHANNEL", "msedge").strip() or "msedge"
        return cls(
            host=os.getenv("HUNTER_HOST", "127.0.0.1"),
            port=_env_int("HUNTER_PORT", 7801),
            # 当前网关会拦截无头浏览器（实测多引擎/多指纹均超时），默认有头
            headless=_env_bool("HUNTER_HEADLESS", False),
            browser_channel=channel,
            call_interval=float(os.getenv("HUNTER_CALL_INTERVAL", "0.35")),
            detail_concurrency=max(1, _env_int("HUNTER_DETAIL_CONCURRENCY", 3)),
            default_interval_sec=max(60, _env_int("HUNTER_DEFAULT_INTERVAL", 300)),
            detail_ttl_hours=max(1, _env_int("HUNTER_DETAIL_TTL_HOURS", 6)),
            proxy=os.getenv("HUNTER_PROXY", "").strip(),
        )


RUNTIME = Runtime.load()
