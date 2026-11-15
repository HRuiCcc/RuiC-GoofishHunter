"""闲鱼接口 → 领域模型的纯函数解析层。

这一层不碰网络、不碰数据库，测试直接喂真实响应样本（tests/fixtures）。
解析与网络、数据库分开，接口字段一变只改这一个文件，测试不启动浏览器。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from hunter.models import ItemCard, ItemDetail, SellerInfo

_CREDIT_MAP = {
    "credit-6": "信用极好",
    "credit-5": "信用优秀",
    "credit-4": "信用良好",
    "credit-3": "信用一般",
}


def dig(node: Any, *keys: str, default: Any = None) -> Any:
    """安全地一层层取字典键，任意一层缺失就返回 default。"""
    current = node
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            index = int(key)
            current = current[index] if index < len(current) else None
        else:
            return default
        if current is None:
            return default
    return current


def as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value).strip().replace("¥", "").replace(",", "").replace("元", "")
    if not text or text.lower() in {"nan", "none", "-", "暂无"}:
        return None
    multiplier = 1.0
    if "万" in text:
        multiplier = 10000.0
        text = text.replace("万", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return round(float(match.group()) * multiplier, 2)


def as_int(value: Any) -> Optional[int]:
    number = as_float(value)
    return int(number) if number is not None else None


def ms_to_iso(value: Any) -> Optional[str]:
    try:
        stamp = int(value)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    if stamp > 10_000_000_000:      # 毫秒
        stamp = stamp // 1000
    return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")


def _price_from_nodes(nodes: Any) -> tuple[Optional[float], str]:
    """搜索列表里的价格是一组富文本节点，拼起来是『¥2700』。"""
    if not isinstance(nodes, list):
        return None, ""
    text = "".join(str(node.get("text", "")) for node in nodes if isinstance(node, dict))
    text = text.replace("当前价", "").strip()
    return as_float(text), text


def _search_tags(args: dict, main: dict) -> list[str]:
    tags: list[str] = []
    raw_tag = str(args.get("tag") or "")
    for token in raw_tag.split("/"):
        token = token.strip()
        if not token:
            continue
        if token == "freeship":
            tags.append("包邮")
        elif token in _CREDIT_MAP:
            tags.append(_CREDIT_MAP[token])
        elif token:
            tags.append(token)
    tag_list = dig(main, "fishTags", "r1", "tagList", default=[]) or []
    for item in tag_list:
        content = dig(item, "data", "content", default="")
        if content and content not in tags:
            tags.append(content)
    return tags


def parse_search_item(raw: dict) -> Optional[ItemCard]:
    main = dig(raw, "data", "item", "main", default={}) or {}
    args = dig(main, "clickParam", "args", default={}) or {}
    content = main.get("exContent") or {}

    item_id = str(content.get("itemId") or args.get("id") or "").strip()
    if not item_id:
        return None

    price, price_text = _price_from_nodes(content.get("price"))
    if price is None:
        price = as_float(args.get("price"))

    link = str(main.get("targetUrl") or "").replace("fleamarket://", "https://www.goofish.com/")
    if not link:
        link = f"https://www.goofish.com/item?id={item_id}"

    pic = str(content.get("picUrl") or "")
    return ItemCard(
        item_id=item_id,
        title=str(content.get("title") or "未知标题").strip(),
        price=price,
        price_display=price_text,
        original_price=as_float(content.get("oriPrice")),
        area=str(content.get("area") or "").strip(),
        seller_id=str(args.get("seller_id") or "").strip(),
        seller_nick=str(content.get("userNickName") or "").strip(),
        publish_at=ms_to_iso(args.get("publishTime")),
        pic=pic,
        pics=[pic] if pic else [],
        tags=_search_tags(args, main),
        category_id=str(args.get("cCatId") or ""),
        want_cnt=as_int(args.get("wantNum")),
        link=link,
        raw=raw,
    )


def parse_search_page(payload: dict, page: int = 1) -> list[ItemCard]:
    items = dig(payload, "data", "resultList", default=[]) or []
    cards: list[ItemCard] = []
    for raw in items:
        card = parse_search_item(raw)
        if card:
            cards.append(card)
    return cards


def _parse_seller(raw: dict) -> Optional[SellerInfo]:
    if not isinstance(raw, dict) or not raw:
        return None
    seller_id = str(raw.get("sellerId") or "").strip()
    if not seller_id:
        return None
    tags: list[str] = []
    for tag in raw.get("identityTags") or []:
        name = (tag.get("trackParams") or {}).get("appearTrackName") or ""
        name = name.replace("Button-", "").strip()
        if name == "Shiren":
            name = "实名认证"
        if name and name not in tags:
            tags.append(name)
    level = as_int(dig(raw, "idleFishCreditTag", "trackParams", "sellerLevel"))
    return SellerInfo(
        seller_id=seller_id,
        nick=str(raw.get("nick") or "").strip(),
        city=str(raw.get("city") or raw.get("publishCity") or "").strip(),
        reg_days=as_int(raw.get("userRegDay")),
        item_count=as_int(raw.get("itemCount")),
        sold_count=as_int(raw.get("hasSoldNumInteger")),
        credit_level=level,
        zhima=bool(raw.get("zhimaAuth")),
        real_name=any("实名" in tag for tag in tags),
        reply_ratio=_percent(raw.get("replyRatio24h")),
        good_ratio=_percent(raw.get("newGoodRatioRate")),
        tags=tags,
        raw=raw,
    )


def _percent(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return round(number * 100, 1) if number <= 1 else round(number, 1)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return round(float(match.group()), 1) if match else None


def parse_detail(payload: dict) -> Optional[ItemDetail]:
    item = dig(payload, "data", "itemDO", default={}) or {}
    item_id = str(item.get("itemId") or "").strip()
    if not item_id:
        return None

    labels: dict[str, str] = {}
    pairs: list[tuple[str, str]] = []
    for label in item.get("itemLabelExtList") or []:
        key = str(label.get("propertyText") or "").strip()
        value = str(label.get("valueText") or "").strip()
        if key and value:
            labels[key] = value
            pairs.append((key, value))

    images = [
        str(image.get("url"))
        for image in (item.get("imageInfos") or [])
        if isinstance(image, dict) and image.get("url")
    ]
    if not images and item.get("defaultPicture"):
        images = [str(item["defaultPicture"])]

    tags = [str(tag.get("text")) for tag in (item.get("commonTags") or []) if tag.get("text")]
    for tag in item.get("priceRelativeTags") or []:
        text = tag.get("text")
        if text and text not in tags:
            tags.append(str(text))

    return ItemDetail(
        item_id=item_id,
        title=str(item.get("title") or "").strip(),
        price=as_float(item.get("soldPrice")),
        original_price=as_float(item.get("originalPrice")),
        desc=str(item.get("desc") or "").strip(),
        city=str(dig(payload, "data", "sellerDO", "city", default="") or ""),
        publish_at=ms_to_iso(item.get("gmtCreate")),
        want_cnt=as_int(item.get("wantCnt")),
        browse_cnt=as_int(item.get("browseCnt")),
        collect_cnt=as_int(item.get("collectCnt")),
        sold_cnt=as_int(item.get("soldCnt")),
        quantity=as_int(item.get("quantity")),
        bargained=bool(item.get("bargained")),
        transport_fee=as_float(item.get("transportFee")),
        status=str(item.get("itemStatusStr") or ""),
        category_id=str(item.get("categoryId") or ""),
        images=images,
        labels=labels,
        label_pairs=pairs,
        seller=_parse_seller(dig(payload, "data", "sellerDO", default={}) or {}),
        raw=payload,
    )


def parse_seller_head(payload: dict) -> Optional[SellerInfo]:
    """卖家主页头部接口：补上信用等级文案、注册地、真实认证。"""
    data = dig(payload, "data", default={}) or {}
    base = dig(data, "module", "base", default={}) or {}
    seller_id = str(dig(data, "baseInfo", "kcUserId", default="") or "")
    if not seller_id:
        return None

    credit_level = None
    credit_text = ""
    for tag in base.get("ylzTags") or []:
        attrs = tag.get("attributes") or {}
        if attrs.get("role") == "seller":
            credit_level = as_int(attrs.get("level"))
            credit_text = str(tag.get("text") or "")

    tags = []
    for key, value in (dig(data, "baseInfo", "tags", default={}) or {}).items():
        if value and "certification" in key:
            tags.append("实名认证")

    return SellerInfo(
        seller_id=seller_id,
        nick=str(base.get("displayName") or ""),
        city=str(base.get("ipLocation") or ""),
        credit_level=credit_level,
        credit_text=credit_text,
        zhima=bool(dig(data, "baseInfo", "tags", "idle_zhima_zheng", default=False)),
        real_name=bool(tags),
        rate_total=as_int(dig(data, "module", "tabs", "rate", "number")),
        item_count=as_int(dig(data, "module", "tabs", "item", "number")),
        tags=tags,
        raw=payload,
    )


def storage_bucket(spec: str) -> str:
    """把 16+512 / 512G / 16+1T 归成同一个可比维度：存储容量。"""
    if not spec:
        return ""
    text = spec.upper().replace("GB", "G")
    match = re.search(r"\+(\d+)\s*(T|G)?$", text)
    if match:
        value, unit = int(match.group(1)), (match.group(2) or "G")
        if unit == "T" or value <= 2:      # 16+1T 这种写法
            return str(value * 1024)
        return str(value)
    match = re.search(r"(\d{3,4})\s*(T|G)?$", text)
    if match:
        value, unit = int(match.group(1)), (match.group(2) or "G")
        return str(value * 1024) if unit == "T" else str(value)
    return ""


def spec_from_text(*texts: str) -> str:
    """从标题/描述里抠规格：16+512、12G+256G、512G 都归一成 16+512 / 512G。"""
    for text in texts:
        if not text:
            continue
        normalized = str(text).replace("＋", "+").replace(" ", "")
        match = re.search(r"(\d{1,2})(?:G|GB)?\+(\d{2,4})(T|G|GB)?", normalized, re.IGNORECASE)
        if match:
            unit = (match.group(3) or "").upper().replace("GB", "G")
            return f"{match.group(1)}+{match.group(2)}{'T' if unit.startswith('T') else ''}"
        match = re.search(r"(\d{3,4})(?:G|GB)(?!\d)", normalized, re.IGNORECASE)
        if match:
            return f"{int(match.group(1))}G"
    return ""
