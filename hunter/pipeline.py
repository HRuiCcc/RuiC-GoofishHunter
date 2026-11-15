"""采集流水线：一次「关注」从搜索到推送的完整路径。

设计要点：
1. 不再每个商品开一个详情页 —— 全部走页面内 mtop 调用；
2. 商品按 item_id 全局去重，同一个商品被多个关注命中只抓一次详情；
3. 先算分再决定要不要问 AI，AI 只处理头部候选；
4. 任何一步失败都写进 runs，页面上能看见卡在哪。
"""
from __future__ import annotations

import asyncio
import json
import traceback
from datetime import datetime
from typing import Optional

from hunter import repo
from hunter.db import init_db
from hunter.config import RUNTIME
from hunter.goofish import parsers
from hunter.goofish.api import GoofishAPI
from hunter.goofish.errors import ApiError, LoginRequired, RiskControl
from hunter.goofish.query import SearchQuery
from hunter.goofish.session import BrowserHub
from hunter.logbus import BUS
from hunter.models import ItemDetail, MarketStats, ScoreResult, SellerInfo, Watch
from hunter.notify import digest_text, format_alert, in_quiet_hours, send
from hunter.scoring import llm
from hunter.scoring.market import build_market
from hunter.scoring.rules import score_item


class Pipeline:
    def __init__(self, hub: Optional[BrowserHub] = None) -> None:
        self.hub = hub or BrowserHub()
        self._running: set[int] = set()
        self._account_sellers_fetched: dict[int, int] = {}

    # ------------------------------------------------------------------ 入口
    async def run_watch(self, watch_id: int, trigger: str = "manual") -> dict:
        init_db()
        watch = repo.watch_get(watch_id)
        if watch is None:
            raise ValueError(f"关注 {watch_id} 不存在")
        if watch_id in self._running:
            BUS.emit("warn", f"「{watch.name}」正在运行，跳过本次触发", watch=watch.name)
            return {"skipped": True, "reason": "running"}

        self._running.add(watch_id)
        self._account_sellers_fetched[watch_id] = 0
        run_id = repo.run_start(watch_id)
        stats = {"found": 0, "new": 0, "scored": 0, "alerted": 0, "failed_detail": 0}
        BUS.emit("info", f"开始扫描「{watch.name}」：{watch.keyword}", watch=watch.name, run=run_id)

        account = self._account_for(watch)
        try:
            # 同一个账号的页面只能被一轮扫描使用：否则一轮在导航、另一轮在 evaluate，
            # 页面会被互相关掉（TargetClosedError）或把网关打成超时。
            async with self.hub.session_lock(account):
                await self.hub.ensure_login(account, keyword=watch.keyword)
                api = GoofishAPI(self.hub, account)

                cards = await self._collect(api, watch)
                stats["found"] = len(cards)
                samples, fresh_cards = self._persist(watch, cards)
                stats["new"] = len(fresh_cards)
                BUS.emit(
                    "info",
                    f"本轮 {len(cards)} 条，其中新上/降价 {len(fresh_cards)} 条",
                    watch=watch.name,
                )

                fresh_ids = {card.item_id for card in fresh_cards}
                scored = await self._score_all(api, watch, cards, fresh_ids, samples)
                stats["scored"] = len(scored)

                alerts = await self._notify(watch, scored)
                stats["alerted"] = len(alerts)

                account_row = repo.account_get_by_name(account)
                if account_row:
                    repo.account_set_status(account_row["id"], "ok")
                # 把这一轮刷新过的 token 写回登录态，下次启动优先用新的
                try:
                    await self.hub.save_state(account)
                except Exception:  # noqa: BLE001
                    pass
                repo.run_finish(run_id, status="ok", **stats)
                BUS.emit("ok", f"「{watch.name}」完成：{len(scored)} 条已评分，{len(alerts)} 条推送", watch=watch.name)
                return {"run_id": run_id, "status": "ok", **stats}

        except LoginRequired as exc:
            return self._fail(run_id, watch, "login", f"登录态失效：{exc}", stats)
        except RiskControl as exc:
            return self._fail(run_id, watch, "risk", f"触发风控：{exc}（建议停 1–2 小时再跑）", stats)
        except ApiError as exc:
            return self._fail(run_id, watch, "error", f"接口返回错误：{exc}", stats)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._fail(run_id, watch, "error", f"{type(exc).__name__}: {exc}", stats)
        finally:
            self._running.discard(watch_id)
            repo.watch_touch_run(watch_id)

    def _fail(self, run_id: int, watch: Watch, status: str, message: str, stats: dict) -> dict:
        BUS.emit("error", message, watch=watch.name, run=run_id)
        repo.run_finish(run_id, status=status, error=message, **stats)
        if status in {"login", "risk"}:
            account = repo.account_get_by_name(self._account_for(watch))
            if account:
                repo.account_set_status(account["id"], status, message)
        return {"run_id": run_id, "status": status, "error": message, **stats}

    # ------------------------------------------------------------------ 步骤
    def _account_for(self, watch: Watch) -> str:
        if watch.account_id:
            account = repo.account_get(watch.account_id)
            if account:
                return account["name"]
        accounts = repo.accounts_list()
        if accounts:
            return accounts[0]["name"]
        repo.account_ensure("default")
        return "default"

    async def _collect(self, api: GoofishAPI, watch: Watch) -> list:
        query = SearchQuery(
            keyword=watch.keyword,
            sort=watch.sort,
            personal_only=watch.personal_only,
            free_shipping=watch.free_shipping,
            min_price=watch.min_price,
            max_price=watch.max_price,
            page_size=watch.page_size,
        )
        collected, seen = [], set()
        for page in range(1, max(1, watch.pages) + 1):
            cards = await api.search_page(query, page)
            if not cards:
                BUS.emit("info", f"第 {page} 页没有结果，停止翻页", watch=watch.name)
                break
            for card in cards:
                if card.item_id in seen:
                    continue
                seen.add(card.item_id)
                collected.append(card)
            BUS.emit("info", f"第 {page} 页抓到 {len(cards)} 条", watch=watch.name)
            if len(cards) < watch.page_size:
                break
        return collected

    def _persist(self, watch: Watch, cards: list) -> tuple[list[tuple[float, str]], list]:
        fresh: list = []
        for card in cards:
            repo.item_upsert_card(card)
            last_price = repo.snapshot_last_price(card.item_id, watch.id)
            first_time = not repo.snapshot_seen_in_watch(card.item_id, watch.id)
            price_changed = last_price is not None and card.price is not None and abs(last_price - card.price) > 0.01
            if card.price is not None and (first_time or price_changed):
                repo.snapshot_add(card.item_id, watch.id, card.price, card.want_cnt)
            if first_time or price_changed:
                fresh.append(card)
        # 按「存储容量」归桶，12+256 与 16+512 各自和自己的同类比
        samples = [
            (price, parsers.storage_bucket(spec))
            for price, spec in repo.market_prices(watch.id, days=30)
        ]
        return samples, fresh

    async def _score_all(self, api: GoofishAPI, watch: Watch, cards: list,
                         fresh_ids: set[str], samples) -> list[dict]:
        # 没评过分、或者本轮新上/降价的才需要重算；这样即使上一轮中断，下一轮也会补上
        pending = [
            card for card in cards
            if card.item_id in fresh_ids or repo.score_get(card.item_id, watch.id) is None
        ]
        if not pending:
            return []
        settings = repo.settings_all()
        min_samples = int(settings.get("min_samples") or 4)
        semaphore = asyncio.Semaphore(RUNTIME.detail_concurrency)
        scored: list[dict] = []

        async def worker(card):
            async with semaphore:
                return await self._score_one(api, watch, card, samples, min_samples, settings)

        for result in await asyncio.gather(*(worker(card) for card in pending), return_exceptions=True):
            if isinstance(result, Exception):
                BUS.emit("warn", f"评分失败：{result}", watch=watch.name)
                continue
            if result:
                scored.append(result)
        scored.sort(key=lambda entry: entry["score"]["score"], reverse=True)
        return scored

    async def _score_one(self, api, watch, card, samples, min_samples, settings) -> Optional[dict]:
        item = repo.item_get(card.item_id)
        if item is None:
            return None

        detail = self._load_detail(item)
        cached_detail = detail is not None
        if detail is None and repo.item_needs_detail(item, RUNTIME.detail_ttl_hours):
            try:
                detail = await api.detail(card.item_id)
            except (LoginRequired, RiskControl):
                raise
            except Exception as exc:  # noqa: BLE001
                BUS.emit("warn", f"详情抓取失败 {card.item_id}：{exc}", watch=watch.name)
                detail = None
            if detail:
                repo.item_apply_detail(detail)
                item = repo.item_get(card.item_id) or item
        if detail is not None and cached_detail:
            # 缓存详情也要回写：补标签、补卖家的数字 ID，但不刷新缓存时间
            repo.item_apply_detail(detail, touch=False)
            item = repo.item_get(card.item_id) or item

        labels = detail.labels if detail else (item.get("labels_json") or {})
        desc = detail.desc if detail else (item.get("desc") or "")
        spec = (detail.spec if detail else item.get("spec_key") or "") or parsers.spec_from_text(
            item.get("title", ""), desc
        )
        if spec and not item.get("spec_key"):
            repo.item_set_spec(card.item_id, spec)
            item["spec_key"] = spec
        seller = await self._seller_for(api, detail, item, settings, watch)

        bucket = parsers.storage_bucket(spec)
        market = build_market(samples, item_spec=bucket, min_samples=min_samples)
        result = score_item(
            title=item.get("title", ""),
            price=item.get("price"),
            market=market,
            labels=labels,
            desc=desc,
            seller=seller,
            publish_at=item.get("publish_at"),
            want_cnt=item.get("want_cnt"),
            transport_fee=item.get("transport_fee"),
            keyword=watch.keyword,
            spec=spec,
        )
        repo.score_upsert(card.item_id, watch.id, result)
        BUS.emit(
            "score",
            f"{result.score} 分 · {result.verdict} · {item.get('title', '')[:26]}",
            watch=watch.name,
            item=card.item_id,
            score=result.score,
        )
        return {
            "item": item,
            "score": self._score_dict(result),
            "detail": detail,
            "seller": seller,
            "result": result,
        }

    def _load_detail(self, item: dict) -> Optional[ItemDetail]:
        raw = item.get("detail_json")
        if not raw:
            return None
        try:
            return parsers.parse_detail(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            return None

    async def _seller_for(self, api, detail, item, settings, watch) -> Optional[SellerInfo]:
        seller = detail.seller if detail else None
        seller_id = seller.seller_id if seller else (item.get("seller_id") or "")
        if not seller_id:
            return seller
        cached = repo.seller_get(seller_id)
        if cached:
            merged = _merge_seller(seller, cached)
            if seller:
                repo.seller_upsert(merged)   # 缓存里的老记录会随每次详情补齐
            return merged
        if seller:
            repo.seller_upsert(seller)
        # 卖家主页只补一次，且限制每轮条数，避免第一轮就把时间花在这上面
        budget = int(settings.get("seller_head_budget") or 10)
        run_budget = self._account_sellers_fetched.setdefault(watch.id or 0, 0)
        if run_budget >= budget:
            return seller
        try:
            head = await api.seller_head(seller_id)
        except (LoginRequired, RiskControl):
            raise
        except Exception:  # noqa: BLE001
            return seller
        self._account_sellers_fetched[watch.id or 0] = run_budget + 1
        if head and seller:
            seller.credit_text = head.credit_text or seller.credit_text
            seller.credit_level = head.credit_level or seller.credit_level
            seller.real_name = seller.real_name or head.real_name
            seller.zhima = seller.zhima or head.zhima
            seller.city = seller.city or head.city
            seller.tags = list(dict.fromkeys([*seller.tags, *head.tags]))
        merged = head or seller
        if merged:
            repo.seller_upsert(merged)
        return merged

    def _score_dict(self, result: ScoreResult) -> dict:
        market = result.market or MarketStats()
        return {
            "score": result.score,
            "verdict": result.verdict,
            "reasons": result.reasons,
            "flags": result.flags,
            "breakdown": result.breakdown,
            "discount_pct": result.discount_pct,
            "market_median": market.median,
            "market_count": market.count,
            "market_basis": market.basis,
        }

    # ------------------------------------------------------------------ 通知
    async def _notify(self, watch: Watch, scored: list[dict]) -> list[dict]:
        if not scored or not watch.notify:
            return []
        settings = repo.settings_all()
        targets = [entry for entry in scored if entry["score"]["score"] >= watch.min_score]
        if not targets:
            return []

        await self._adjudicate_all(watch, scored, settings)
        targets = [entry for entry in scored if entry["score"]["score"] >= watch.min_score]
        if not targets:
            return []

        quiet = in_quiet_hours(settings.get("quiet_hours") or "")
        sent: list[dict] = []
        for entry in targets:
            item, score = entry["item"], entry["score"]
            price = item.get("price")
            if repo.alert_exists(item["item_id"], watch.id, price):
                continue
            title, body = format_alert(item, score)
            payload = {"title": title, "body": body, "quiet": quiet}
            if quiet:
                repo.alert_add(item["item_id"], watch.id, price, score["score"], "quiet", True, payload)
                BUS.emit("info", "静默时段，已收进站内提醒", watch=watch.name)
                sent.append(entry)
                continue
            results = await send(title, body, settings)
            ok = any(results.values()) if results else False
            repo.alert_add(item["item_id"], watch.id, price, score["score"],
                           ",".join(results) or "console", ok or not results, payload)
            sent.append(entry)

        # 一次超过 3 条时再补一条汇总，避免刷屏
        if len([e for e in sent]) > 3 and settings.get("digest_enabled", "1") == "1" and not quiet:
            title, body = digest_text(sent)
            await send(title, body, settings)
        return sent

    async def _adjudicate_all(self, watch: Watch, scored: list[dict], settings: dict) -> None:
        if not watch.use_llm or not llm.enabled(settings):
            return
        limit = int(settings.get("llm_top_n") or 6)
        candidates = [entry for entry in scored if entry["score"]["score"] >= 60][:limit]
        if not candidates:
            return
        BUS.emit("info", f"AI 复核 {len(candidates)} 条候选", watch=watch.name)

        semaphore = asyncio.Semaphore(3)

        async def run(entry):
            async with semaphore:
                result = entry["result"]
                payload = await llm.adjudicate(
                    title=entry["item"].get("title", ""),
                    price=entry["item"].get("price"),
                    detail=entry["detail"],
                    seller=entry["seller"],
                    market=result.market or MarketStats(),
                    result=result,
                    settings=settings,
                )
                if payload:
                    repo.score_set_llm(entry["item"]["item_id"], watch.id, payload)
                    entry["score"]["llm"] = payload

        await asyncio.gather(*(run(entry) for entry in candidates), return_exceptions=True)


def _merge_seller(base: Optional[SellerInfo], cached: dict) -> SellerInfo:
    merged = SellerInfo(
        seller_id=cached["seller_id"],
        nick=cached.get("nick") or "",
        city=cached.get("city") or "",
        reg_days=cached.get("reg_days"),
        item_count=cached.get("item_count"),
        sold_count=cached.get("sold_count"),
        credit_level=cached.get("credit_level"),
        credit_text=cached.get("credit_text") or "",
        zhima=bool(cached.get("zhima")),
        real_name=bool(cached.get("real_name")),
        reply_ratio=cached.get("reply_ratio"),
        good_ratio=cached.get("good_ratio"),
        rate_total=cached.get("rate_total"),
        tags=cached.get("tags") or [],
    )
    if base:
        merged.nick = merged.nick or base.nick
        merged.city = merged.city or base.city
        merged.reg_days = base.reg_days or merged.reg_days
        merged.sold_count = base.sold_count or merged.sold_count
        merged.item_count = base.item_count or merged.item_count
        merged.reply_ratio = base.reply_ratio or merged.reply_ratio
        merged.good_ratio = base.good_ratio or merged.good_ratio
        merged.credit_level = base.credit_level or merged.credit_level
        merged.zhima = merged.zhima or base.zhima
        merged.real_name = merged.real_name or base.real_name
        merged.city = merged.city or base.city
        merged.tags = list(dict.fromkeys([*merged.tags, *base.tags]))
    return merged
