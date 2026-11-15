"""Web 服务：本地单用户，只绑 127.0.0.1。"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hunter import __version__, repo
from hunter.config import PATHS, PROJECT_ROOT, RUNTIME
from hunter.db import init_db
from hunter.goofish.api import GoofishAPI
from hunter.goofish.query import SearchQuery
from hunter.goofish.session import BrowserHub
from hunter.logbus import BUS
from hunter.login import check_login, interactive_login
from hunter.models import Watch, now_iso
from hunter.pipeline import Pipeline
from hunter.scheduler import Scheduler
from hunter.scoring.market import build_market

HUB = BrowserHub()
PIPELINE = Pipeline(HUB)
SCHEDULER = Scheduler(PIPELINE)
LOGIN_TASKS: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    PATHS.ensure()
    await SCHEDULER.start()
    BUS.emit("info", f"闲鱼猎手启动，数据目录 {PATHS.data}")
    yield
    await SCHEDULER.stop()
    await HUB.close()


app = FastAPI(title="闲鱼猎手", version=__version__, lifespan=lifespan)


# --------------------------------------------------------------------------- 入参
class WatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    keyword: str = Field(min_length=1, max_length=120)
    sort: str = "newest"
    pages: int = Field(default=2, ge=1, le=10)
    personal_only: bool = True
    free_shipping: bool = True
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_score: int = Field(default=60, ge=0, le=100)
    interval_sec: int = Field(default=300, ge=60, le=86400)
    use_llm: bool = True
    notify: bool = True
    note: str = ""


class WatchPatch(BaseModel):
    name: Optional[str] = None
    keyword: Optional[str] = None
    sort: Optional[str] = None
    pages: Optional[int] = Field(default=None, ge=1, le=10)
    personal_only: Optional[bool] = None
    free_shipping: Optional[bool] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_score: Optional[int] = Field(default=None, ge=0, le=100)
    interval_sec: Optional[int] = Field(default=None, ge=60, le=86400)
    use_llm: Optional[bool] = None
    notify: Optional[bool] = None
    note: Optional[str] = None


class FeedbackIn(BaseModel):
    feedback: str = Field(pattern="^(good|bad|deal|)$")
    note: str = ""


class SettingsIn(BaseModel):
    values: dict[str, Any]


# --------------------------------------------------------------------------- 基础
@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "version": __version__,
        "time": now_iso(),
        "data_dir": str(PATHS.data),
        "headless": RUNTIME.headless,
        "browser": RUNTIME.browser_channel,
    }


@app.get("/api/overview")
async def overview():
    stats = repo.overview_stats()
    stats["trend"] = repo.price_trend(days=14)
    stats["top"] = repo.items_list(min_score=0, limit=6, order="score")
    return stats


# --------------------------------------------------------------------------- 关注
@app.get("/api/watches")
async def list_watches():
    watches = []
    for watch in repo.watch_list():
        data = watch.__dict__.copy()
        data["item_count"] = repo.items_count(watch.id)
        runs = [run for run in repo.runs_list(50) if run["watch_id"] == watch.id]
        data["last_run"] = runs[0] if runs else None
        watches.append(data)
    return watches


@app.post("/api/watches", status_code=201)
async def create_watch(payload: WatchIn):
    watch = Watch(**payload.model_dump())
    created = repo.watch_create(watch)
    BUS.emit("info", f"新建关注「{created.name}」：{created.keyword}")
    return created.__dict__


@app.patch("/api/watches/{watch_id}")
async def patch_watch(watch_id: int, payload: WatchPatch):
    if repo.watch_get(watch_id) is None:
        raise HTTPException(404, "关注不存在")
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    repo.watch_update(watch_id, fields)
    watch = repo.watch_get(watch_id)
    return watch.__dict__ if watch else {}


@app.delete("/api/watches/{watch_id}", status_code=204)
async def delete_watch(watch_id: int):
    repo.watch_delete(watch_id)
    return Response(status_code=204)


@app.post("/api/watches/{watch_id}/run")
async def run_watch(watch_id: int):
    if repo.watch_get(watch_id) is None:
        raise HTTPException(404, "关注不存在")
    asyncio.create_task(PIPELINE.run_watch(watch_id, trigger="manual"))
    return {"started": True}


# --------------------------------------------------------------------------- 商品
@app.get("/api/items")
async def list_items(
    watch_id: Optional[int] = None,
    min_score: int = 0,
    search: str = "",
    limit: int = Query(default=40, le=200),
    offset: int = 0,
    order: str = "score",
    feedback: str = "",
):
    items = repo.items_list(
        watch_id=watch_id, min_score=min_score, search=search,
        limit=limit, offset=offset, order=order, feedback=feedback,
    )
    return {"items": items, "total": repo.items_count(watch_id)}


@app.get("/api/items/{item_id}")
async def get_item(item_id: str, watch_id: Optional[int] = None):
    item = repo.item_get(item_id)
    if item is None:
        raise HTTPException(404, "商品不存在")
    scores = []
    with repo.db() as conn:  # 这个商品在所有关注下的评分
        rows = conn.execute("SELECT * FROM scores WHERE item_id = ? ORDER BY score DESC", (item_id,)).fetchall()
    for row in rows:
        entry = dict(row)
        for key in ("breakdown_json", "flags_json", "reasons_json"):
            try:
                entry[key] = json.loads(entry[key] or "null")
            except json.JSONDecodeError:
                entry[key] = None
        if entry.get("llm_json"):
            try:
                entry["llm"] = json.loads(entry["llm_json"])
            except json.JSONDecodeError:
                entry["llm"] = None
        scores.append(entry)
    seller = repo.seller_get(item.get("seller_id") or "")
    return {
        "item": item,
        "scores": scores,
        "snapshots": repo.snapshot_series(item_id),
        "seller": seller,
    }


@app.post("/api/items/{item_id}/feedback")
async def item_feedback(item_id: str, payload: FeedbackIn):
    if repo.item_get(item_id) is None:
        raise HTTPException(404, "商品不存在")
    repo.item_set_feedback(item_id, payload.feedback, payload.note)
    return {"ok": True}


# --------------------------------------------------------------------------- 卖家 / 运行
@app.get("/api/sellers/{seller_id}")
async def get_seller(seller_id: str):
    seller = repo.seller_get(seller_id)
    if not seller:
        raise HTTPException(404, "卖家缓存中没有这条记录")
    return seller


@app.get("/api/runs")
async def list_runs(limit: int = 30):
    return repo.runs_list(limit)


# --------------------------------------------------------------------------- 账号
@app.get("/api/accounts")
async def list_accounts():
    accounts = repo.accounts_list()
    return [
        {
            **account,
            "logged_in": account.get("status") == "ok",
            "has_state": (PATHS.states / f"{account['name']}.json").exists(),
        }
        for account in accounts
    ]


@app.post("/api/accounts/{name}/login")
async def start_login(name: str):
    repo.account_ensure(name)
    if name in LOGIN_TASKS and not LOGIN_TASKS[name].done():
        return {"started": False, "reason": "已有登录窗口在等待"}

    async def runner():
        result = await interactive_login(HUB, name)
        account = repo.account_get_by_name(name)
        if account:
            repo.account_set_status(account["id"], "ok" if result.get("ok") else "expired",
                                    result.get("error"))
        return result

    LOGIN_TASKS[name] = asyncio.create_task(runner())
    return {"started": True}


@app.get("/api/accounts/{name}/status")
async def login_status(name: str):
    task = LOGIN_TASKS.get(name)
    if task and not task.done():
        return {"pending": True, "detail": "等待扫码"}
    state = await check_login(HUB, name)
    return {"pending": False, **state}


@app.post("/api/accounts/{name}/import")
async def import_login(name: str, payload: dict):
    path = payload.get("path") or ""
    if not Path(path).expanduser().exists():
        raise HTTPException(400, "登录态文件不存在")
    repo.account_ensure(name)
    count = await HUB.import_state(name, str(Path(path).expanduser()))
    awaited = await check_login(HUB, name)
    account = repo.account_get_by_name(name)
    if account:
        repo.account_set_status(account["id"], "ok" if awaited.get("logged_in") else "expired")
    return {"imported": count, **awaited}


# --------------------------------------------------------------------------- 预览 / 设置
@app.post("/api/preview")
async def preview(payload: WatchIn):
    """不落库的试抓：让用户在保存关注前先看看能抓到什么。"""
    accounts = repo.accounts_list()
    account = accounts[0]["name"] if accounts else "default"
    repo.account_ensure(account)
    api = GoofishAPI(HUB, account)
    query = SearchQuery(
        keyword=payload.keyword, sort=payload.sort,
        personal_only=payload.personal_only, free_shipping=payload.free_shipping,
        min_price=payload.min_price, max_price=payload.max_price,
    )
    try:
        await HUB.ensure_login(account)
        cards = await api.search_page(query, 1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"试抓失败：{exc}") from exc
    prices = [(card.price, "") for card in cards if card.price]
    market = build_market(prices, item_spec="", min_samples=1)
    return {
        "count": len(cards),
        "median": market.median,
        "minimum": market.minimum,
        "maximum": market.maximum,
        "items": [card.__dict__ | {"raw": None} for card in cards[:12]],
        "filter": query.search_filter,
    }


@app.get("/api/settings")
async def get_settings():
    values = repo.settings_all()
    has_key = bool(values.get("llm_api_key"))
    values.pop("llm_api_key", None)
    has_tg = bool(values.get("telegram_token"))
    values.pop("telegram_token", None)
    return {**values, "has_llm_key": has_key, "has_telegram_token": has_tg}


@app.put("/api/settings")
async def put_settings(payload: SettingsIn):
    values = {k: v for k, v in payload.values.items() if v is not None}
    if "llm_api_key" in values and values["llm_api_key"] in {"", "••••••"}:
        values.pop("llm_api_key")
    repo.settings_set(values)
    return {"ok": True}


# --------------------------------------------------------------------------- 实时日志
@app.get("/api/events")
async def events():
    async def stream():
        yield "retry: 5000\n\n"
        async for event in BUS.subscribe():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        # 兜底，正常不会到这里

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/logs")
async def logs(limit: int = 200):
    return BUS.recent(limit)


# --------------------------------------------------------------------------- 静态资源
DIST = PROJECT_ROOT / "webui" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    async def placeholder():
        return JSONResponse(
            status_code=503,
            content={"error": "前端还没构建，先在 webui/ 里执行 npm install && npm run build"},
        )


def serve() -> None:
    import uvicorn

    init_db()
    uvicorn.run(app, host=RUNTIME.host, port=RUNTIME.port, log_level="info")
