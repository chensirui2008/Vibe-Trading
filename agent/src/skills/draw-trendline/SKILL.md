---
name: draw-trendline
description: Draw auditable price trendlines for a trading symbol with a mandatory weekly-chart-first, daily-chart-second workflow. Connect only same-side swing points, keep wick/body anchoring consistent, require a third touch for validation, reject forced fits, and return both charts plus anchor evidence. Use for 趋势线绘制, 画趋势线, 周线日线趋势分析, trendline chart, support trendline, or resistance trendline requests. This is chart analysis only and never places trades.
category: analysis
---

# Draw Trendline

为单个交易标的绘制可复核的趋势线。执行顺序固定为：**先生成周线图并完成周线趋势线判断，再生成日线图**。不得跳过周线直接从日线寻找一条“看起来合适”的线。

本技能只做图表分析，不下单，也不把趋势线触碰直接解释为买卖建议。

## 必需输入与默认值

- `symbol`：必须解析为唯一代码；名称或代码有歧义时先调用 `search_symbol`，未锁定唯一标的就停止。
- `as_of`：默认最近一个完整交易日；盘中 K 线不得与完整日线混用。
- `anchor_mode`：默认 `wick`，可选 `body`。同一次分析的周线和日线必须使用相同模式。
- `price_scale`：默认 `linear`，可选 `log`。不得根据结果好坏静默切换坐标尺度。
- 默认观察窗口：周线至少 156 根完整周 K；日线至少 250 根完整日 K。数据不足时明确报告实际覆盖，不得补零或伪造。

## 数据获取与周线聚合

1. 使用 `get_market_data` 获取足够覆盖周线窗口的完整日线 OHLCV：

   ```text
   codes=[resolved_symbol]
   interval="1D"
   source="auto"
   max_rows=0
   start_date=<至少早于 as_of 三年>
   end_date=<as_of>
   ```

2. 检查日期严格递增、无重复日期、OHLC 为正且满足 `Low <= min(Open, Close) <= max(Open, Close) <= High`。缺失或非法数据直接报错，不得以前值、零值或另一个代码替代。
3. `get_market_data` 不提供周线参数，因此必须由同一份日线数据本地聚合周线，保持同一来源、复权口径和截止日：

   ```python
   weekly = daily.resample("W-FRI", label="right", closed="right").agg(
       {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
   ).dropna(subset=["open", "high", "low", "close"])
   ```

4. 若 `as_of` 所在周尚未完成，周线图排除该不完整周；日线图仍以最近一个完整交易日为截止日。必须在输出中分别记录两个截止日。
5. 不得为周线和日线分别换用不同数据源；若源发生变化，停止并重新取得统一口径数据。

## 趋势线定义

### 1. 只连接同一侧的转折点

- 上升支撑线：只连接两个显著低点，并要求第二个低点高于第一个低点。
- 下降阻力线：只连接两个显著高点，并要求第二个高点低于第一个高点。
- 禁止把高点和低点连接在同一条趋势线上。

默认用局部摆动点减少主观性：周线左右各 2 根 K，日线左右各 3 根 K。边界处尚未获得右侧确认的 K 线不能作为已确认摆动点。

### 2. 两点定义，三点验证

- 第一点是趋势起点，第二点固定斜率；固定后不得为了迎合后续价格移动锚点。
- 两个触点只能得到 `candidate` 趋势线。
- 第二点之后至少出现一次独立触碰并产生同向反应，才标为 `validated`。
- 触碰按价格区域判断，而非要求一个完全相同的像素点。默认容差为：

  ```text
  tolerance = max(0.5 * ATR14, 0.5% * 当期价格)
  ```

- 同一摆动簇内连续相邻 K 线只算一次触碰，防止把一次盘整误算成多次验证。

### 3. 影线与实体保持一致

- `anchor_mode=wick`：上升线使用 `Low`，下降线使用 `High`。
- `anchor_mode=body`：上升线使用 `min(Open, Close)`，下降线使用 `max(Open, Close)`。
- 周线、日线和所有触点统计都必须沿用同一 `anchor_mode`；不得第一点取影线、第二点取实体。

### 4. 拒绝强行拟合

在所有符合方向条件的锚点对中，按以下优先级选择：

1. `validated` 优先于只有两个触点的 `candidate`；
2. 独立有效触点更多；
3. 穿越 K 线实体或有效收盘破线的次数更少；
4. 两锚点时间跨度更长；
5. 在以上条件相同的情况下，优先仍覆盖当前价格区域的线。

支撑线若多次位于实体上方、阻力线若多次位于实体下方，说明它切穿价格主体，应淘汰。一次短暂越界后迅速收回可以保留，但必须标注为 `breach_and_reclaim`，不能当作正常触碰。

没有自然满足上述条件的趋势线时，输出 `no_clear_trendline`。仍可生成纯 K 线图并标注“无清晰趋势线”，但禁止移动锚点或放大容差来制造结果。

## 强制执行顺序

### 第一阶段：周线图

1. 从聚合后的完整周线中识别摆动高低点。
2. 分别评估上升支撑线和下降阻力线，只保留证据更强的主要趋势线；两者都清晰时可以同时绘制，但必须分别列出证据。
3. 先保存周线图，并确认文件存在且非空。
4. 记录周线方向、锚点日期/价格、第三触点、有效触点数、破线次数、状态和坐标尺度。
5. 周线图未成功生成时立即停止，不得继续生成日线图。

### 第二阶段：日线图

1. 只有周线阶段完成后才进入日线阶段。
2. 将周线趋势线投影到日线图，使用灰色虚线并标注 `weekly projection`。
3. 在日线数据上按相同规则独立寻找更细粒度的日线趋势线，不得为了与周线结论一致而移动日线锚点。
4. 若日线与周线方向不同，标注 `timeframe_divergence` 并同时保留两者；不得隐藏冲突。
5. 保存日线图，并确认文件存在且非空。

## 图表规范

- 必须使用 OHLC K 线，不得用单一收盘折线冒充 K 线图。
- 周线图标题：`<symbol> Weekly Trendline (as of <date>)`。
- 日线图标题：`<symbol> Daily Trendline (as of <date>)`。
- 上升支撑线使用绿色，下降阻力线使用红色；`candidate` 用虚线，`validated` 用实线。
- 明确标出 Anchor 1、Anchor 2 和第三次验证触点；趋势线延伸到图表右端，但不得把未来延长段计入触点。
- 图例必须包含方向、`candidate/validated` 状态、`anchor_mode` 和 `price_scale`。
- 默认文件名：

  ```text
  <symbol>_weekly_trendline.png
  <symbol>_daily_trendline.png
  ```

- 所有图表写入当前 run/artifact 目录；不得写入技能源码目录或覆盖用户原文件。

## 输出顺序

先展示周线图，再展示日线图，最后给出证据表：

```markdown
## 周线趋势线
![weekly chart](<absolute-path>)

## 日线趋势线
![daily chart](<absolute-path>)

| 周期 | 方向 | Anchor 1 | Anchor 2 | 第三触点 | 有效触点 | 实体穿越/有效破线 | 状态 |
|---|---|---|---|---|---:|---:|---|
| 周线 | 上升支撑/下降阻力/无 | 日期@价格 | 日期@价格 | 日期@价格或无 | N | N | validated/candidate/no_clear_trendline |
| 日线 | 上升支撑/下降阻力/无 | 日期@价格 | 日期@价格 | 日期@价格或无 | N | N | validated/candidate/no_clear_trendline |

- 数据源与复权口径：
- 周线截止日 / 日线截止日：
- anchor_mode / price_scale：
- 周日线是否冲突：
- 数据限制或异常：
```

## 失败与边界

- 标的无法唯一解析、OHLCV 无效、历史不足或周线图写入失败时，明确报错并停止；错误不得静默通过。
- 不使用未来 K 线确认历史时点的摆动点；若用户要求历史回看，所有摆动确认和第三触点只能使用当时已完成的 K 线。
- 趋势线是分析区域，不是精确成交价；不得仅凭第三次触碰给出保证收益、必涨必跌或个性化投资建议。
- 不调用交易、账户写入、下单或撤单工具。
