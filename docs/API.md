# 前端接口契约（v0.1）

后端：`http://127.0.0.1:7801`，所有路径以 `/api` 开头，JSON，无鉴权（只绑本机）。
开发时 Vite 把 `/api` 代理到 7801。

## 概览

`GET /api/overview`

```json
{
  "total_items": 128, "today_items": 14, "today_runs": 6, "alerts_today": 3,
  "avg_score": 61.2, "active_watches": 2,
  "by_verdict": {"强烈推荐": 4, "值得看": 12, "观望": 30, "放弃": 8},
  "last_run": {"started_at": "2026-11-15T10:40:00", "status": "ok"},
  "best": {"title": "...", "price": 2100, "score": 88},
  "trend": [{"day": "2026-11-14", "n": 60, "avg_price": 2480.2, "min_price": 2100}],
  "top": [<item 对象，见下>]
}
```

## 关注（watch）

`GET /api/watches` → 数组，每项：

```json
{
  "id": 1, "name": "vivo X200 Pro", "keyword": "vivo x200 pro", "account_id": null,
  "sort": "newest", "pages": 2, "page_size": 30,
  "personal_only": true, "free_shipping": true,
  "min_price": null, "max_price": null, "min_score": 60, "interval_sec": 300,
  "enabled": true, "use_llm": true, "notify": true, "note": "",
  "created_at": "...", "last_run_at": "...", "next_run_at": "...",
  "item_count": 42, "last_run": {<run 对象>} | null
}
```

- `POST /api/watches` body = 名称/关键词/筛选/间隔等（name、keyword 必填），返回创建后的对象。
- `PATCH /api/watches/{id}` 局部更新。
- `DELETE /api/watches/{id}` → 204。
- `POST /api/watches/{id}/run` → `{"started": true}`（后台异步跑，进度看 `/api/events`）。

`POST /api/preview` body 同创建关注，返回试抓结果（不落库）：

```json
{"count": 30, "median": 2580, "minimum": 2100, "maximum": 3400,
 "filter": "quickFilter:filterPersonal,filterFreePostage;",
 "items": [{"item_id": "...", "title": "...", "price": 2400, "area": "江苏",
            "seller_nick": "...", "publish_at": "...", "tags": ["包邮"], "pic": "http://..."}]}
```

## 商品

`GET /api/items?watch_id=1&min_score=60&search=&limit=40&offset=0&order=score|new|price|discount&feedback=`

返回 `{"items": [...], "total": 128}`，item 列为商品行 + 评分列：

```json
{
  "item_id": "1094...", "title": "...", "price": 2400, "price_display": "¥2400",
  "area": "江苏", "seller_id": "...", "seller_nick": "...", "publish_at": "2026-11-15 09:20",
  "first_seen_at": "...", "last_seen_at": "...", "pics_json": ["url"], "tags_json": ["包邮"],
  "labels_json": {"成色": "几乎全新", "存储容量": "512GB"}, "spec_key": "16+512",
  "want_cnt": 3, "transport_fee": 0, "status": "在线", "link": "https://www.goofish.com/item?id=...",
  "feedback": null, "feedback_note": null,
  "score": 82, "verdict": "强烈推荐", "discount_pct": 18.4, "market_median": 2600,
  "market_count": 9, "flags_json": ["包邮"], "reasons_json": ["比同规格中位价低 18.4%（...）"],
  "breakdown_json": {"价格": 23.5, "成色": 9.9, "卖家": 5.4, "风险": -2},
  "llm": {"verdict": "buy", "summary": "...", "ask_seller": "..."} | null
}
```

注意：数据库列名就是 `pics_json` / `labels_json` / `flags_json` / `reasons_json` / `breakdown_json`，
但值已经解码成数组/对象（不是字符串）。

`GET /api/items/{item_id}` → `{"item": {...}, "scores": [...], "snapshots": [...], "seller": {...}}`

`scores[]` 每项：`{"watch_id", "score", "verdict", "market_median", "market_p25", "market_count",
"discount_pct", "breakdown_json", "flags_json", "reasons_json", "llm_json", "llm"}`。

`POST /api/items/{item_id}/feedback` body `{"feedback": "good|bad|deal|", "note": ""}`。

## 运行 / 账号 / 设置

- `GET /api/runs?limit=30` → `[{"id","watch_id","watch_name","keyword","started_at","finished_at","found","new_items","scored","alerted","status","error","stats"}]`
- `GET /api/accounts` → `[{"id","name","status","last_ok_at","last_error","logged_in","has_state"}]`
- `POST /api/accounts/{name}/login` → 打开扫码窗口，返回 `{"started": true}`
- `GET /api/accounts/{name}/status` → `{"pending": bool, "logged_in": bool, "detail": "..."}`
- `POST /api/accounts/{name}/import` body `{"path": "/abs/path.json"}`
- `GET /api/settings` → 键值对 + `has_llm_key`（密钥不回传）
- `PUT /api/settings` body `{"values": {...}}`
- `GET /api/sellers/{seller_id}`
- `GET /api/health`

## 实时日志

`GET /api/events` → SSE，`data: {"ts":"10:41:02","level":"info|ok|warn|error|score","msg":"...","watch":"...","run":3,"score":82}`

EventSource 会自动重连；页面打开后先补发最近 50 条。

`GET /api/logs?limit=200` → 同样的数组（用于首屏）。
