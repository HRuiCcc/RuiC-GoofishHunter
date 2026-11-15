# 接口笔记：搜索、详情与风控边界

这份笔记记录闲鱼网页端三个接口的调用方式、参数编码和踩过的坑。
所有结论都来自本机真实页面调试（2026-11-15），代码在 `hunter/goofish/`。

## 1. 端点

主机：`https://h5api.m.goofish.com/h5/<api>/1.0/`

| 用途 | API | 关键参数 |
|---|---|---|
| 搜索 | `mtop.taobao.idlemtopsearch.pc.search` | `data` 为 JSON 字符串，含关键词、分页、筛选 |
| 详情 | `mtop.taobao.idle.pc.detail` | `{"itemId":"..."}` |
| 卖家头部 | `mtop.idle.web.user.page.head` | `{"userId":"..."}` |

## 2. 搜索请求体

```json
{
  "pageNumber": 1,
  "keyword": "vivo x200 pro",
  "fromFilter": true,
  "rowsPerPage": 30,
  "sortField": "create",
  "sortValue": "desc",
  "propValueStr": {
    "searchFilter": "priceRange:2000,3000;quickFilter:filterPersonal,filterFreePostage;"
  },
  "searchReqFromPage": "pcSearch",
  "extraFilterValue": "{}",
  "userPositionJson": "{}"
}
```

筛选条件的编码规则（逐项在页面里核对过）：

| 条件 | `searchFilter` 片段 |
|---|---|
| 个人闲置 | `quickFilter:filterPersonal;` |
| 包邮 | `quickFilter:filterPersonal,filterFreePostage;` |
| 最低价 2000 | `priceRange:2000,undefined;quickFilter:...;` |
| 价格 2000–3000 | `priceRange:2000,3000;quickFilter:...;` |
| 最新发布 | `sortField=create, sortValue=desc, fromFilter=true` |
| 价格升序 | `sortField=price, sortValue=asc` |

多个条件用 `;` 连接，`priceRange` 排在 `quickFilter` 前面。空条件是空字符串，仍然带 `propValueStr` 字段。

参数拼装实现：`hunter/goofish/query.py`（有单测逐字锁住格式）。

## 3. 列表卡字段

搜索结果 `data.resultList[]`，每条的 `data.item.main` 下：

| 位置 | 字段 |
|---|---|
| `exContent` | `itemId`、`title`、`price`（富文本节点数组）、`area`、`userNickName`、`picUrl`、`oriPrice` |
| `clickParam.args` | `seller_id`、`publishTime`（毫秒）、`wantNum`、`tag`（如 `freeship/credit-6`）、`cCatId`、`id` |
| `targetUrl` | `fleamarket://...`，需替换成 `https://www.goofish.com/...` |

价格是 `[{text:"¥"},{text:"2700"}]` 这样的节点数组，拼起来再转数字。

## 4. 详情里被低估的字段

`data.itemDO` 除了标题/价格，还有：

- `itemLabelExtList`：**结构化标签**，`propertyText` 是「成色 / 存储容量 / 运行内存 / 版本 / 拆修和功能 / 品牌 / 型号」，`valueText` 是值。
  成色、规格、版本、拆修这些不用从描述里猜，直接读。
- `desc`：卖家原文描述，风险词主要从这里扫。
- `gmtCreate`、`wantCnt`、`browseCnt`、`collectCnt`、`soldCnt`、`quantity`、`bargained`、`transportFee`、`itemStatusStr`、`imageInfos`。

`data.sellerDO` 有：

- `userRegDay`（注册天数）、`itemCount`（在售数）、`replyRatio24h`、`newGoodRatioRate`
- `zhimaAuth`、`identityTags`（实名认证）、`levelTags`、`city`、`sellerItems`
- `idleFishCreditTag.trackParams.sellerLevel`（信用等级数字）

卖家主页头部接口补充：`ylzTags` 里的 `卖家信用极好/优秀` 文案、`ipLocation`、评价总数。

## 5. 返回码与处理

`ret` 形如 `["SUCCESS::调用成功"]`。

| 返回 | 含义 | 处理 |
|---|---|---|
| `RGV587_ERROR::SM` | 风控拦截 | 停止该轮，冷却后再试 |
| `FAIL_SYS_USER_VALIDATE` | 要过验证 | 停止，提示人工处理 |
| `FAIL_SYS_TRAFFIC_LIMIT` | 限流 | 停止并降低频率 |
| `FAIL_SYS_TOKEN_EXOIRED` / `TOKEN_EMPTY` | token 过期 | 刷新页面重取 `_m_h5_tk` 后重试一次 |
| `FAIL_BIZ_*` | 业务参数错误 | 记录，不重试 |
| `TIMEOUT::接口超时` | 见第 6 节 | — |

## 6. 三条硬约束（实测）

1. **裸 HTTP 直连会被拦**：带 cookie 手算 `sign` 直接 POST，返回 `RGV587_ERROR::SM`。
   必须借页面里的 `window.lib.mtop.request`，它自带签名与安全头。
2. **无头 + 默认 UA 会被挂起**：`headless=True` 且 UA 含 `HeadlessChrome/HeadlessEdg` 时，
   搜索稳定返回 `TIMEOUT::接口超时`；把 UA 换成真实 Chrome UA 后无头正常 `SUCCESS`。
3. **`type` 必须小写 `post`**：传 `POST` / `ORIGINALJSON` 会得到 `UNEXCEPT_REQUEST::错误的请求类型`。

## 7. 调用姿势

```js
await window.lib.mtop.request({
  api: 'mtop.taobao.idlemtopsearch.pc.search',
  v: '1.0', type: 'post', dataType: 'json',
  data: { /* 上面那份 JSON */ }
})
// → {ret: ['SUCCESS::调用成功'], data: {resultList: [...30 条...]}}
```

单次调用约 0.3–0.8 秒。30 条详情 + 30 条搜索约 20–40 秒；详情缓存后一轮 3–4 秒。

## 8. 自保策略

- 每次调用间隔 0.35 秒 + 抖动
- 详情并发 3
- 同时最多 2 个关注在跑
- 命中验证码/限流立即停止，不换号硬刚
- 每个账号一个浏览器 profile，跨进程文件锁防止并发抢占

