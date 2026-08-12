---
name: breakout-scan
description: Screen US stocks for Qullamaggie-style breakout candidates using 1-, 3-, and 6-month relative strength plus a 2-week to 2-month tightening base, higher lows, contracting volume, rising 10/20-day averages, and a confirmed swing-high pivot. Use whenever the user asks to select stocks, scan candidates, build a watchlist, or find setups for a breakout strategy, 突破策略选股, 强势股平台突破, 突破候选, or Qullamaggie breakout. This skill is for candidate selection, not entry timing or order placement.
---

# Breakout Scan

筛选 Qullamaggie Setup 1 的美股候选。只做候选识别和排序；除非用户另行要求，不生成入场、止损、仓位、退出规则，不下单。

## 默认口径

- 市场：美股（NASDAQ、NYSE、NYSE American）。
- 标的：普通股与 ADR；排除 ETF、基金、权证、优先股、OTC 和无法确认类型的代码。
- 截止日：最近一个完整交易日。盘中数据不得与完整日线混算。
- 复权：收益率和均线使用复权日线；成交量使用数据源提供的对应日线口径。
- 股票池：优先使用用户指定股票池；否则默认使用当前 S&P 500 成分代理。它不是美股全市场，也不是历史无偏股票池。必须报告股票池名称、成分日期、总数、成功取数数和失败代码。

禁止把 `screen_market` 返回的当日涨幅榜、热门股列表或当前 S&P 500 成分代理冒充“美股全市场”。默认结果必须称为“当前 S&P 500 成分代理排名”。无法获得该股票池时停止，不得使用手选 fallback 或静默缩小范围。

## 工作流

### 1. 锁定数据与覆盖

1. 先锁定明确的 `as_of` 日期。用户未指定股票池时，必须调用 `screen_momentum(as_of=..., universe="sp500")`；用户指定代码时，必须把代码传给同一工具的 `symbols` 参数。
2. `screen_momentum` 负责批量取得复权日线、锁定共同完整交易日，并计算 21/63/126 日横截面排名。不要让模型逐只下载股票再手工排名。
3. 只对工具返回的三个周期前 2% 并集继续执行后续上涨段、平台和 pivot 检查。不得自行补入未入选股票。
4. 检查工具返回的股票池来源、成分日期、分母、共同截止日和 `failed_symbols`。若默认 S&P 500 成分加载失败，停止，不得改用 `screen_market` 或手选名单。
5. 后续需要完整 OHLCV 判断平台时，再仅对初筛候选调用 `get_market_data`，使用 `source="auto"`、`interval="1D"`，并确保 `max_rows` 不做间隔抽样。不同来源不一致时报告差异，不得拼接。

### 2. 相对强度初筛

`screen_momentum` 在每只股票最后一个共同有效交易日计算：

```text
R21  = Close[t] / Close[t-21]  - 1
R63  = Close[t] / Close[t-63]  - 1
R126 = Close[t] / Close[t-126] - 1
```

分别在同一股票池内按 `R21`、`R63`、`R126` 降序做百分位排名：

- 核心池：任一周期进入前 1%。
- 观察池：未进前 1%，但任一周期进入前 2%。
- 样本太小导致 1% 少于 1 只时，至少保留排名第 1；必须同时展示名次和分母。
- 不得把三个收益率平均后再宣称“前 1%–2%”；三个周期的横截面排名必须分别保留。
- 后续输出必须沿用工具返回的名次和有效样本分母，不由模型重新估算百分位。

### 3. 第一段上涨

对初筛股票识别平台开始前 1–3 个月的上涨段，优先保留：

- 累计涨幅约 `30%–100%+`；
- 上涨持续数天至数周，而非只有一天的脉冲；
- 上涨段结束后才进入平台整理。

原策略没有规定唯一的上涨段算法。必须展示所用起止日期和涨幅；若无法稳定识别，标为 `needs_review`，不得伪造精确结论。

### 4. 平台结构

寻找持续 `10–42` 个交易日（约 2 周–2 个月）的整理区间，并逐项检查：

1. **波动收窄**：后半段真实波幅/ADR 低于前半段，且最近短窗波动不扩张。
2. **低点抬高**：至少两个已确认摆动低点，后一个高于前一个。
3. **成交量收缩**：平台后半段成交量中位数低于前半段；单日异常量必须单列说明。
4. **均线向上**：10 日和 20 日均线均上升，价格主要运行在其附近或上方；偶尔回踩 50 日线不自动淘汰。50 日线不是原策略硬门槛。
5. **明确平台上沿**：上沿必须对应已确认的摆动高点，不能用任意近期最高价代替。

默认用 `3-3 pivot` 把“已确认摆动点”操作化：某根 K 线的高点严格高于左右各 3 根 K 线的高点，低点严格低于左右各 3 根 K 线的低点。右侧 3 根尚未完成时，摆动点未确认。若用户指定其他 pivot 结构，保留其定义并重新计算。

### 5. 接近突破的可执行排序

以平台内最近且清晰的已确认摆动高点作为 `pivot_price`：

```text
distance_to_pivot = Close[t] / pivot_price - 1
```

默认只把尚未突破且距离 pivot 不超过 5% 的股票标为 `ready`；5% 是为了形成可执行观察名单的操作阈值，不是 Qullamaggie 原文硬规则。其他合格平台保留为 `forming`。已经明显突破或远离 pivot 的股票标为 `extended_or_triggered`，不得混进“待突破”名单。

排序优先级：

1. 进入前 1% 的周期数；
2. 三个周期中最好的百分位及名次；
3. 平台条件通过数；
4. 距 pivot 的绝对距离更小；
5. 数据完整度更高。

不得把成交量放大作为候选期硬门槛；突破日放量属于触发验证，不属于本 skill 的平台选股条件。

## 失败与边界

- 不调用交易、账户写入或下单工具。
- 不因数据缺失自动改用更小股票池、较短窗口或未经确认的 pivot。
- QVeris 等可能计费的数据调用必须先说明预计成本并获得用户明确同意；未同意就不用。
- 当前指数成分只能标注为“当前成分代理”，不能称为历史无偏股票池。
- 若股票池、行情覆盖或复权口径不足以支持结论，返回 `无法完成可靠筛选`，列出缺失项和下一步，而不是输出猜测名单。

## 输出格式

先给结论和候选名单，再给方法与限制：

```markdown
## 突破候选（as of YYYY-MM-DD）

| 排名 | 代码 | 状态 | R21名次 | R63名次 | R126名次 | 上涨段 | 平台天数 | Pivot | 距Pivot | 结构证据 | 风险/缺口 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|

### 排除但接近的股票
| 代码 | 排除原因 | 缺失或失败的标准 |

### 数据与覆盖
- 截止日：
- 股票池及成分日期：
- 股票池总数 / 成功 / 失败：
- 数据源与复权口径：
- 失败代码：
- 操作化定义：3-3 pivot、5% ready 阈值及任何用户覆盖值
```

每个入选项都要给出可核查的日期和数值证据。将结果称为研究/观察名单，不作保证收益或直接买入建议。

来源方法：Qullamaggie，[My 3 Timeless Setups That Have Made Me Tens of Millions](https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/)，Setup 1 Breakout。
