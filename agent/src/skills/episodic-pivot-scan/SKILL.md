---
name: episodic-pivot-scan
description: Screen US stocks for Qullamaggie-style Episodic Pivot candidates after an unexpected material event, requiring a verified catalyst, a gap of at least 10%, exceptional volume, positive price confirmation, and limited prior 3- to 6-month anticipation. Use when the user asks for 事件驱动交易选股, 事件驱动选股, 财报跳空选股, 重大事件跳空, Episodic Pivot, EP scan, or stocks being repriced after earnings, guidance, FDA, or regulatory news. Do not use for general event research, merger arbitrage, or event-driven portfolio construction without a gap-repricing stock-selection request. This skill selects candidates only; it does not place trades.
---

# Episodic Pivot Scan

筛选 Qullamaggie Setup 2（Episodic Pivot，简称 EP）的美股候选。核心链条是：

```text
意外且重大的新信息 → 至少 10% 跳空 → 异常成交量 → 开盘后价格确认
```

只做候选识别和排序。除非用户另行要求，不生成入场、止损、仓位或退出规则，不下单。

## 默认口径

- 市场：美股（NASDAQ、NYSE、NYSE American）的普通股与 ADR。
- 时间：同时报告 UTC、美国东部时间和数据截止时间；区分盘前、开盘后与收盘后结果。
- 事件：财报、业绩指引、FDA/临床结果、监管决定，或足以改变公司盈利路径的其他公司级消息。
- 排除：ETF、基金、权证、优先股、OTC、纯市场传闻、无公司级催化的跟风上涨。
- 盘前结果只能叫 `provisional`；开盘后成交量和价格尚未确认前，不得叫合格 EP。

这是事件候选扫描，不要求预先拥有完整美股历史股票池，但必须披露事件源/异动榜的覆盖范围。不得把有限新闻源或 `screen_market(top_n<=100)` 的结果称为“全市场完整扫描”。

## 工作流

### 1. 发现候选并锁定可知时间

1. 优先从用户指定事件列表、官方公告/财报日历或盘前异动列表发现候选；盘中可用 Vibe-Trading 的 `screen_market(market="us", sort_by="change_pct")` 补充发现，但它只返回有限的当前涨幅榜。
2. 对每个候选记录事件首次公开时间、时区、来源 URL 和市场所处阶段。盘后发布的事件只能影响下一交易日，禁止回填到当日。
3. 用公司投资者关系页面、SEC 文件、FDA/监管机构公告等一手来源确认事件正文。`get_stock_news` 可用于发现线索，不能仅凭聚合标题认定催化内容。
4. 同一事件的转载必须去重。若不同来源的发布时间或关键数字冲突，保留冲突并标为 `needs_review`。

无法确认“是什么新信息、何时首次可知”时，停止该候选的评估，不用价格异动反推故事。

### 2. 验证事件是否构成意外重估

每个候选必须回答：

- 市场原先预期是什么？
- 新信息相对预期改变了什么？
- 这是公司级、可持续的重估，还是一次性/低信息量消息？

财报型 EP 优先检查：

- EPS 同比增速及实际值相对一致预期的 surprise；
- 营收同比增速及实际值相对一致预期的 surprise；
- 管理层是否上调指引，以及新指引相对旧指引和一致预期的位置；
- 增长是否来自主营业务，而非税率、回购或一次性项目。

原策略偏好 EPS 处于中高双位数或三位数增长、营收高速增长、明显超预期且指引上调的事件，但没有给出一套通用数值阈值。必须展示原始实际值、同比值、预期值和来源；缺少一致预期时写 `consensus_unavailable`，不得把同比增长冒充“超预期”。

非财报事件必须说明其可量化影响和不确定性。只有新闻情绪、没有基本面或监管事实支撑的候选标为 `headline_only` 并排除。

### 3. 验证至少 10% 跳空

使用同一上市标的、同一复权口径的前一完整交易日收盘价：

```text
premarket_gap = PremarketPrice / PreviousClose - 1
open_gap      = OfficialOpen / PreviousClose - 1
```

- 盘前筛选：`premarket_gap >= 10%` 才进入 `provisional`。
- 开盘后确认：必须报告 `open_gap`；`open_gap < 10%` 则不满足原策略硬门槛，即使盘前一度超过 10%。
- `get_market_data` 可取得历史/日内 OHLCV，但必须确认最新日线是否完整、分钟线是否覆盖盘前，以及 `max_rows` 是否导致间隔抽样。
- 当前涨跌幅、盘前涨幅和正式开盘跳空是三个不同指标，不得互相替代。

缺少官方开盘价或前收盘价时标为 `gap_unverified`，不得四舍五入凑足 10%。

### 4. 验证异常成交量

以事件日前 20 个完整交易日的日成交量中位数作为默认 `ADV20`：

```text
ADV20              = median(Volume[t-20:t-1])
volume_progress_15 = cumulative_regular_volume_first_15m / ADV20
volume_progress_30 = cumulative_regular_volume_first_30m / ADV20
```

- 原策略最强候选往往在开盘后 15–30 分钟内已成交接近日均量。
- 默认把 `volume_progress_30 >= 1.0` 标为 `exceptional`；这是对“接近日均量”的可审计操作定义，不是原文新增硬门槛。
- 盘前成交量单独报告，不得混入常规时段前 15/30 分钟累计量。
- 若数据只有日线，候选最多保持 `volume_unverified`，不能用当日最终总量伪装成开盘 30 分钟量。

同时报告成交量源、时间戳和覆盖时段。数据源不含扩展时段时必须明确说明。

### 5. 检查过去 3–6 个月是否已提前反映

取得至少 126 个完整交易日的复权日线，计算：

```text
R63_pre_event  = PreviousClose / Close[t-63]  - 1
R126_pre_event = PreviousClose / Close[t-126] - 1
```

优先过去 3–6 个月没有提前大涨、关注度较低的股票。原策略没有定义“已大涨”的统一百分比，因此：

- 必须展示 `R63_pre_event`、`R126_pre_event` 和事件前价格路径；
- 不以自创阈值自动淘汰；若已有持续多月强势趋势，标为 `anticipated_or_extended` 并降低排名；
- 事件日跳空不得计入这两个事件前收益率。

### 6. 开盘后价格确认

EP 不是“有利好就买”。开盘后必须观察价格是否接受更高估值：

- `confirmed`：正式开盘跳空至少 10%，成交量验证通过，价格守住开盘区间且继续向上确认。
- `provisional`：盘前满足事件和 10% 跳空，但尚未开盘。
- `watch`：事件和跳空成立，但成交量尚未达到或数据尚不完整。
- `failed_reaction`：跳空后持续抛售、跌破所观察开盘区间低点，或好消息没有价格响应。

若用户没有指定开盘区间周期，筛选阶段同时报告首个 5 分钟和 30 分钟区间，不自行选择交易触发周期。候选 skill 不输出买点。

## 排序

按以下顺序排序，不合成为无法解释的黑箱分数：

1. 事件证据完整且 surprise 可量化；
2. 正式开盘跳空满足 10%，幅度更明确；
3. 前 15/30 分钟成交量进度更强；
4. 开盘后价格确认更强；
5. 过去 3–6 个月较少提前反映；
6. 数据覆盖更完整。

财报数字“看起来很好”但价格不响应的股票必须排在已确认候选之后，或直接归入 `failed_reaction`。

## 失败与边界

- 不调用交易、账户写入或下单工具。
- 不因数据缺失静默放宽 10% 跳空、时间戳、事件来源或成交量要求。
- QVeris 等可能计费的数据调用必须先说明预计成本并获得用户明确同意；未同意就不用。
- 实时/盘前数据具有时效性；输出必须带精确 `as_of`，过期后重新取数。
- 无法获得可靠事件 feed 时返回实际覆盖范围，不声称完整扫描。
- 若事件、跳空或成交量三项任一无法验证，明确给出 `无法确认合格 EP` 及缺失项，不输出猜测性买入建议。

## 输出格式

先给候选，再披露证据与覆盖：

```markdown
## Episodic Pivot 候选（as of YYYY-MM-DD HH:MM ET）

| 排名 | 代码 | 状态 | 事件及首次可知时间 | 关键 Surprise | 盘前跳空 | 开盘跳空 | 15m/30m量÷ADV20 | 开盘后确认 | 3m/6m事前涨幅 | 风险/缺口 |
|---:|---|---|---|---|---:|---:|---:|---|---:|---|

### 排除或待确认
| 代码 | 状态 | 排除/缺失原因 |

### 数据与覆盖
- 截止时间及市场阶段：
- 事件发现源及覆盖范围：
- 一手来源：
- 价格/成交量来源与时段：
- 成功候选 / 失败代码：
- 操作化定义：ADV20、volume_progress_30 及任何用户覆盖值
```

每个入选项都要给出可核查的时间、数值和来源。将结果称为研究/观察名单，不作保证收益或直接买入建议。

来源方法：Qullamaggie，[My 3 Timeless Setups That Have Made Me Tens of Millions](https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/)，Setup 2 Episodic Pivot。
