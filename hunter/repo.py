"""数据读写：所有 SQL 收在这里，上层只认这些函数。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from hunter.db import db
from hunter.models import (
    ItemCard,
    ItemDetail,
    MarketStats,
    ScoreResult,
    SellerInfo,
    Watch,
    now_iso,
)


# --------------------------------------------------------------------------- 设置
def settings_all() -> dict[str, str]:
    with db() as conn:
        return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


def settings_get(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def settings_set(values: dict[str, Any]) -> None:
    with db() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, "" if value is None else str(value)),
            )


# --------------------------------------------------------------------------- 账号
def accounts_list() -> list[dict]:
    with db() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM accounts ORDER BY id")]


def account_get(account_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return dict(row) if row else None


def account_ensure(name: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO accounts(name, profile_dir, status, created_at) VALUES (?, ?, 'unknown', ?)",
            (name, name, now_iso()),
        )
        row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        return dict(row)


def account_get_by_name(name: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def account_set_status(account_id: int, status: str, error: str | None = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE accounts SET status = ?, last_error = ?, last_ok_at = CASE WHEN ? = 'ok' "
            "THEN ? ELSE last_ok_at END WHERE id = ?",
            (status, error, status, now_iso(), account_id),
        )


# --------------------------------------------------------------------------- 关注
def watch_create(watch: Watch) -> Watch:
    with db() as conn:
        cursor = conn.execute(
            """INSERT INTO watches(name, keyword, account_id, sort, pages, page_size,
                personal_only, free_shipping, min_price, max_price, min_score, interval_sec,
                enabled, use_llm, notify, note, created_at, next_run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                watch.name, watch.keyword, watch.account_id, watch.sort, watch.pages,
                watch.page_size, int(watch.personal_only), int(watch.free_shipping),
                watch.min_price, watch.max_price, watch.min_score, watch.interval_sec,
                int(watch.enabled), int(watch.use_llm), int(watch.notify), watch.note,
                watch.created_at, now_iso(),
            ),
        )
        watch.id = cursor.lastrowid
    return watch


def watch_list() -> list[Watch]:
    with db() as conn:
        return [Watch.from_row(row) for row in conn.execute("SELECT * FROM watches ORDER BY id")]


def watch_get(watch_id: int) -> Optional[Watch]:
    with db() as conn:
        row = conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
    return Watch.from_row(row) if row else None


WATCH_UPDATABLE = {
    "name", "keyword", "account_id", "sort", "pages", "page_size", "personal_only",
    "free_shipping", "min_price", "max_price", "min_score", "interval_sec", "enabled",
    "use_llm", "notify", "note",
}


def watch_update(watch_id: int, fields: dict[str, Any]) -> None:
    payload = {k: v for k, v in fields.items() if k in WATCH_UPDATABLE}
    if not payload:
        return
    for key in ("personal_only", "free_shipping", "enabled", "use_llm", "notify"):
        if key in payload:
            payload[key] = int(bool(payload[key]))
    columns = ", ".join(f"{key} = ?" for key in payload)
    with db() as conn:
        conn.execute(f"UPDATE watches SET {columns} WHERE id = ?", (*payload.values(), watch_id))


def watch_delete(watch_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))


def watch_touch_run(watch_id: int) -> None:
    now = datetime.now()
    with db() as conn:
        row = conn.execute("SELECT interval_sec FROM watches WHERE id = ?", (watch_id,)).fetchone()
        interval = int(row["interval_sec"]) if row else 300
        conn.execute(
            "UPDATE watches SET last_run_at = ?, next_run_at = ? WHERE id = ?",
            (now.isoformat(timespec="seconds"),
             (now + timedelta(seconds=interval)).isoformat(timespec="seconds"),
             watch_id),
        )


def watches_due() -> list[Watch]:
    now = now_iso()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM watches WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?) "
            "ORDER BY id",
            (now,),
        ).fetchall()
    return [Watch.from_row(row) for row in rows]


# --------------------------------------------------------------------------- 商品
def item_get(item_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
    return _decode_item(row) if row else None


def item_upsert_card(card: ItemCard, detail: Optional[ItemDetail] = None) -> bool:
    """写入或刷新一张商品卡。返回 True 表示这是第一次见到这个商品。"""
    now = now_iso()
    labels = detail.labels if detail else {}
    with db() as conn:
        existing = conn.execute("SELECT item_id FROM items WHERE item_id = ?", (card.item_id,)).fetchone()
        is_new = existing is None
        if is_new:
            conn.execute(
                """INSERT INTO items(item_id, title, price, price_display, original_price, area,
                    seller_id, seller_nick, publish_at, first_seen_at, last_seen_at, pics_json,
                    tags_json, labels_json, spec_key, want_cnt, link)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    card.item_id, card.title, card.price, card.price_display, card.original_price,
                    card.area, card.seller_id, card.seller_nick, card.publish_at, now, now,
                    json.dumps(card.pics or ([card.pic] if card.pic else []), ensure_ascii=False),
                    json.dumps(card.tags, ensure_ascii=False),
                    json.dumps(labels, ensure_ascii=False),
                    detail.spec if detail else "", card.want_cnt, card.link,
                ),
            )
        else:
            # 列表页没有描述和规格标签，不能在刷新列表卡时把它们抹掉
            labels_text = json.dumps(labels, ensure_ascii=False)
            spec_text = detail.spec if detail else ""
            conn.execute(
                """UPDATE items SET title = ?, price = COALESCE(?, price),
                    price_display = COALESCE(NULLIF(?, ''), price_display), last_seen_at = ?,
                    area = ?, seller_nick = ?,
                    seller_id = CASE WHEN seller_id = '' THEN ? ELSE seller_id END,
                    pics_json = CASE WHEN ? != '[]' THEN ? ELSE pics_json END,
                    tags_json = ?, want_cnt = ?, link = ?,
                    labels_json = CASE WHEN ? != '{}' THEN ? ELSE labels_json END,
                    spec_key = CASE WHEN ? != '' THEN ? ELSE spec_key END
                   WHERE item_id = ?""",
                (
                    card.title, card.price, card.price_display, now, card.area,
                    card.seller_nick, card.seller_id,
                    json.dumps(card.pics or ([card.pic] if card.pic else []), ensure_ascii=False),
                    json.dumps(card.pics or ([card.pic] if card.pic else []), ensure_ascii=False),
                    json.dumps(card.tags, ensure_ascii=False), card.want_cnt, card.link,
                    labels_text, labels_text, spec_text, spec_text, card.item_id,
                ),
            )
    return is_new


def item_apply_detail(detail: ItemDetail, *, touch: bool = True) -> None:
    """touch=False 用于把缓存详情里的标签补写回商品表，不刷新缓存时间。"""
    now = now_iso()
    seller_id = detail.seller.seller_id if detail.seller else ""
    seller_nick = detail.seller.nick if detail.seller else ""
    with db() as conn:
        conn.execute(
            f"""UPDATE items SET title = ?, desc = ?, labels_json = ?, spec_key = ?,
                want_cnt = ?, browse_cnt = ?, collect_cnt = ?, transport_fee = ?, status = ?,
                original_price = COALESCE(?, original_price), detail_json = ?,
                detail_at = CASE WHEN ? THEN ? ELSE detail_at END,
                pics_json = CASE WHEN ? != '[]' THEN ? ELSE pics_json END,
                seller_id = CASE WHEN ? != '' THEN ? ELSE seller_id END,
                seller_nick = CASE WHEN ? != '' THEN ? ELSE seller_nick END
               WHERE item_id = ?""",
            (
                detail.title or "", detail.desc,
                json.dumps(detail.labels, ensure_ascii=False), detail.spec,
                detail.want_cnt, detail.browse_cnt, detail.collect_cnt, detail.transport_fee,
                detail.status, detail.original_price,
                json.dumps(detail.raw, ensure_ascii=False),
                int(touch), now,
                json.dumps(detail.images, ensure_ascii=False),
                json.dumps(detail.images, ensure_ascii=False),
                seller_id, seller_id, seller_nick, seller_nick,
                detail.item_id,
            ),
        )


def item_needs_detail(item: dict, ttl_hours: int) -> bool:
    detail_at = item.get("detail_at")
    if not detail_at:
        return True
    try:
        seen = datetime.fromisoformat(detail_at)
    except ValueError:
        return True
    return datetime.now() - seen > timedelta(hours=ttl_hours)


def item_set_spec(item_id: str, spec: str) -> None:
    if not spec:
        return
    with db() as conn:
        conn.execute(
            "UPDATE items SET spec_key = ? WHERE item_id = ? AND (spec_key IS NULL OR spec_key = '')",
            (spec, item_id),
        )


def item_set_feedback(item_id: str, feedback: str, note: str = "") -> None:
    with db() as conn:
        conn.execute(
            "UPDATE items SET feedback = ?, feedback_note = ?, feedback_at = ? WHERE item_id = ?",
            (feedback or None, note, now_iso(), item_id),
        )


def items_list(
    *,
    watch_id: Optional[int] = None,
    min_score: int = 0,
    search: str = "",
    limit: int = 60,
    offset: int = 0,
    order: str = "score",
    feedback: str = "",
) -> list[dict]:
    where = ["1=1"]
    params: list[Any] = []
    if watch_id:
        where.append("s.watch_id = ?")
        params.append(watch_id)
    if min_score:
        where.append("COALESCE(s.score, 0) >= ?")
        params.append(min_score)
    if search:
        where.append("(i.title LIKE ? OR i.desc LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if feedback:
        where.append("i.feedback = ?")
        params.append(feedback)

    order_sql = {
        "score": "COALESCE(s.score, 0) DESC, i.first_seen_at DESC",
        "new": "i.first_seen_at DESC",
        "price": "i.price ASC",
        "discount": "COALESCE(s.discount_pct, 0) DESC",
    }.get(order, "COALESCE(s.score, 0) DESC")

    sql = f"""
        SELECT i.*, s.score, s.verdict, s.discount_pct, s.market_median, s.market_count,
               s.spec_key AS score_spec, s.flags_json, s.reasons_json, s.breakdown_json,
               s.llm_json, s.scored_at, s.watch_id AS score_watch,
               se.credit_text AS seller_credit, se.reg_days AS seller_reg_days,
               se.reply_ratio AS seller_reply_ratio, se.item_count AS seller_item_count
        FROM items i
        LEFT JOIN sellers se ON se.seller_id = i.seller_id
        LEFT JOIN scores s ON s.rowid = (
            SELECT s2.rowid FROM scores s2
            WHERE s2.item_id = i.item_id AND (? IS NULL OR s2.watch_id = ?)
            ORDER BY s2.score DESC LIMIT 1
        )
        WHERE {' AND '.join(where)}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    params = [watch_id, watch_id, *params, limit, offset]
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_decode_item(row) for row in rows]


def items_count(watch_id: Optional[int] = None) -> int:
    with db() as conn:
        if watch_id:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM scores WHERE watch_id = ?", (watch_id,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()
    return int(row["n"])


def _decode_item(row: Any) -> dict:
    data = dict(row)
    for key in ("pics_json", "tags_json", "labels_json", "flags_json", "reasons_json", "breakdown_json"):
        if key in data and isinstance(data[key], str):
            try:
                data[key] = json.loads(data[key] or "null")
            except json.JSONDecodeError:
                data[key] = None
    if "llm_json" in data and data["llm_json"]:
        try:
            data["llm"] = json.loads(data["llm_json"])
        except json.JSONDecodeError:
            data["llm"] = None
    return data


# --------------------------------------------------------------------------- 快照
def snapshot_add(item_id: str, watch_id: int, price: float, want_cnt: Optional[int]) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        conn.execute(
            "INSERT INTO snapshots(item_id, watch_id, price, want_cnt, seen_at) VALUES (?,?,?,?,?)",
            (item_id, watch_id, price, want_cnt, stamp),
        )


def snapshot_last_price(item_id: str, watch_id: int) -> Optional[float]:
    with db() as conn:
        row = conn.execute(
            "SELECT price FROM snapshots WHERE item_id = ? AND watch_id = ? "
            "ORDER BY seen_at DESC LIMIT 1",
            (item_id, watch_id),
        ).fetchone()
    return float(row["price"]) if row else None


def snapshot_seen_in_watch(item_id: str, watch_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM snapshots WHERE item_id = ? AND watch_id = ? LIMIT 1",
            (item_id, watch_id),
        ).fetchone()
    return row is not None


def snapshot_series(item_id: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT price, want_cnt, seen_at FROM snapshots WHERE item_id = ? "
            "ORDER BY seen_at DESC LIMIT 60",
            (item_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def market_prices(watch_id: int, days: int = 30) -> list[tuple[float, str]]:
    """近 N 天该关注下见过的每个商品的最新价 + 规格指纹。"""
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with db() as conn:
        rows = conn.execute(
            """SELECT i.price AS price, i.spec_key AS spec_key
               FROM items i
               WHERE i.price IS NOT NULL AND i.item_id IN (
                   SELECT item_id FROM snapshots WHERE watch_id = ? AND seen_at >= ?
               )
               GROUP BY i.item_id""",
            (watch_id, since),
        ).fetchall()
    return [(float(row["price"]), row["spec_key"] or "") for row in rows]


# --------------------------------------------------------------------------- 评分
def score_upsert(item_id: str, watch_id: int, result: ScoreResult) -> None:
    market = result.market or MarketStats()
    with db() as conn:
        conn.execute(
            """INSERT INTO scores(item_id, watch_id, score, verdict, market_median, market_p25,
                market_count, discount_pct, spec_key, breakdown_json, flags_json, reasons_json,
                scored_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(item_id, watch_id) DO UPDATE SET
                 score = excluded.score, verdict = excluded.verdict,
                 market_median = excluded.market_median, market_p25 = excluded.market_p25,
                 market_count = excluded.market_count, discount_pct = excluded.discount_pct,
                 spec_key = excluded.spec_key, breakdown_json = excluded.breakdown_json,
                 flags_json = excluded.flags_json, reasons_json = excluded.reasons_json,
                 scored_at = excluded.scored_at""",
            (
                item_id, watch_id, result.score, result.verdict, market.median, market.p25,
                market.count, result.discount_pct, result.spec_key,
                json.dumps(result.breakdown, ensure_ascii=False),
                json.dumps(result.flags, ensure_ascii=False),
                json.dumps(result.reasons, ensure_ascii=False), now_iso(),
            ),
        )


def score_set_llm(item_id: str, watch_id: int, payload: dict) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE scores SET llm_json = ? WHERE item_id = ? AND watch_id = ?",
            (json.dumps(payload, ensure_ascii=False), item_id, watch_id),
        )


def score_get(item_id: str, watch_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM scores WHERE item_id = ? AND watch_id = ?", (item_id, watch_id)
        ).fetchone()
    return _decode_item(row) if row else None


# --------------------------------------------------------------------------- 卖家
def seller_upsert(seller: SellerInfo) -> None:
    with db() as conn:
        conn.execute(
            """INSERT INTO sellers(seller_id, nick, city, reg_days, item_count, sold_count,
                credit_level, credit_text, zhima, real_name, reply_ratio, good_ratio, rate_total,
                tags_json, raw_json, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(seller_id) DO UPDATE SET
                 nick=excluded.nick, city=excluded.city, reg_days=excluded.reg_days,
                 item_count=excluded.item_count, sold_count=excluded.sold_count,
                 credit_level=excluded.credit_level, credit_text=excluded.credit_text,
                 zhima=excluded.zhima, real_name=excluded.real_name,
                 reply_ratio=excluded.reply_ratio, good_ratio=excluded.good_ratio,
                 rate_total=excluded.rate_total, tags_json=excluded.tags_json,
                 raw_json=excluded.raw_json, fetched_at=excluded.fetched_at""",
            (
                seller.seller_id, seller.nick, seller.city, seller.reg_days, seller.item_count,
                seller.sold_count, seller.credit_level, seller.credit_text, int(seller.zhima),
                int(seller.real_name), seller.reply_ratio, seller.good_ratio, seller.rate_total,
                json.dumps(seller.tags, ensure_ascii=False),
                json.dumps(seller.raw, ensure_ascii=False), now_iso(),
            ),
        )


def seller_get(seller_id: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM sellers WHERE seller_id = ?", (seller_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["tags"] = json.loads(data.get("tags_json") or "[]")
    except json.JSONDecodeError:
        data["tags"] = []
    return data


# --------------------------------------------------------------------------- 告警与运行
def alert_exists(item_id: str, watch_id: int, price: Optional[float]) -> bool:
    """同一个商品同一个价格只推一次：分数微调不该重复打扰。"""
    with db() as conn:
        row = conn.execute(
            "SELECT 1 FROM alerts WHERE item_id = ? AND watch_id = ? AND price IS ?",
            (item_id, watch_id, price),
        ).fetchone()
    return row is not None


def alert_add(item_id: str, watch_id: int, price: Optional[float], score: int,
              channel: str, ok: bool, payload: dict) -> None:
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO alerts(item_id, watch_id, price, score, channel, ok, "
            "payload_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (item_id, watch_id, price, score, channel, int(ok),
             json.dumps(payload, ensure_ascii=False), now_iso()),
        )


def run_start(watch_id: int) -> int:
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO runs(watch_id, started_at, status) VALUES (?, ?, 'running')",
            (watch_id, now_iso()),
        )
        return int(cursor.lastrowid)


def run_finish(run_id: int, **fields: Any) -> None:
    allowed = {"found", "new_items", "scored", "alerted", "status", "error", "stats_json"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    if "stats_json" in payload and not isinstance(payload["stats_json"], str):
        payload["stats_json"] = json.dumps(payload["stats_json"], ensure_ascii=False)
    payload["finished_at"] = now_iso()
    columns = ", ".join(f"{key} = ?" for key in payload)
    with db() as conn:
        conn.execute(f"UPDATE runs SET {columns} WHERE id = ?", (*payload.values(), run_id))


def runs_mark_interrupted(message: str = "服务重启，这一轮被中断") -> int:
    """进程退出时没跑完的那一轮，别让它永远停在「进行中」。"""
    with db() as conn:
        cursor = conn.execute(
            "UPDATE runs SET status = 'error', error = ?, finished_at = ? WHERE status = 'running'",
            (message, now_iso()),
        )
        return int(cursor.rowcount)


def runs_list(limit: int = 30) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT r.*, w.name AS watch_name, w.keyword FROM runs r
               LEFT JOIN watches w ON w.id = r.watch_id
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        data = dict(row)
        try:
            data["stats"] = json.loads(data.get("stats_json") or "{}")
        except json.JSONDecodeError:
            data["stats"] = {}
        out.append(data)
    return out


def overview_stats() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    with db() as conn:
        total_items = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
        today_items = conn.execute(
            "SELECT COUNT(*) AS n FROM items WHERE first_seen_at LIKE ?", (f"{today}%",)
        ).fetchone()["n"]
        today_runs = conn.execute(
            "SELECT COUNT(*) AS n FROM runs WHERE started_at LIKE ?", (f"{today}%",)
        ).fetchone()["n"]
        alerts_today = conn.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE created_at LIKE ? AND ok = 1", (f"{today}%",)
        ).fetchone()["n"]
        avg_score = conn.execute("SELECT AVG(score) AS s FROM scores").fetchone()["s"]
        by_verdict = {
            row["verdict"]: row["n"]
            for row in conn.execute("SELECT verdict, COUNT(*) AS n FROM scores GROUP BY verdict")
        }
        last_run = conn.execute("SELECT started_at, status FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        watch_count = conn.execute("SELECT COUNT(*) AS n FROM watches WHERE enabled = 1").fetchone()["n"]
        best = conn.execute(
            """SELECT i.title, i.price, s.score FROM scores s JOIN items i ON i.item_id = s.item_id
               ORDER BY s.score DESC, s.discount_pct DESC LIMIT 1"""
        ).fetchone()
    return {
        "total_items": int(total_items),
        "today_items": int(today_items),
        "today_runs": int(today_runs),
        "alerts_today": int(alerts_today),
        "avg_score": round(float(avg_score), 1) if avg_score else None,
        "by_verdict": by_verdict,
        "active_watches": int(watch_count),
        "last_run": dict(last_run) if last_run else None,
        "best": dict(best) if best else None,
    }


def price_trend(days: int = 14, watch_id: Optional[int] = None) -> list[dict]:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    sql = """SELECT substr(seen_at, 1, 10) AS day, COUNT(*) AS n, AVG(price) AS avg_price,
                    MIN(price) AS min_price
             FROM snapshots WHERE seen_at >= ?"""
    params: list[Any] = [since]
    if watch_id:
        sql += " AND watch_id = ?"
        params.append(watch_id)
    sql += " GROUP BY day ORDER BY day"
    with db() as conn:
        return [dict(row) for row in conn.execute(sql, params)]
