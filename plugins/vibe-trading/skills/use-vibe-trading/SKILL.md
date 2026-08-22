---
name: use-vibe-trading
description: Routes finance and trading-research requests to the right Vibe-Trading skills, then uses the bundled MCP tools to carry out the selected guidance. Use when a user asks to use Vibe-Trading, needs market research, screening, strategy design, backtesting, portfolio or risk analysis, or is unsure which Vibe-Trading capability fits the task.
---

# Use Vibe-Trading

Treat this skill as the router for Vibe-Trading's finance skill catalog. Select the methodology first; call tools only after the relevant skill has been loaded.

## Routing workflow

1. Extract the task's market, asset class, research objective, required artifact, time horizon, and constraints. Ask only for missing details that would change the skill choice.
2. Call `list_skills` and treat its current names, descriptions, and categories as the source of truth. Do not rely on a memorized catalog count.
3. Choose one primary skill whose description most specifically matches the requested outcome. Add a supporting skill only when it owns a separate part of the task.
4. Call `load_skill` with the exact returned name before doing that part of the work. Continue paginated reads when the loaded content says more remains.
5. Follow the loaded skill's workflow and use the Vibe-Trading MCP tools it names. Inspect the exposed tool schema instead of inventing arguments.
6. If no catalog entry matches, use the smallest direct Vibe-Trading tool that satisfies the request and say that no dedicated skill was selected.

Do not load a large bundle of vaguely related skills. A precise primary skill plus zero to two supporting skills is the normal case.

## Routing map

Use this map to form a shortlist, then confirm every name and description with `list_skills`.

| User intent | Start with | Common supporting skills |
| --- | --- | --- |
| Fetch or choose market data | `data-routing` | The selected provider skill, such as `yfinance`, `eastmoney`, `okx-market`, `akshare`, `mootdx`, `sec-edgar`, or `qveris` |
| Company, earnings, or valuation research | `research-discipline` plus the most specific analysis skill | `financial-statement`, `valuation-model`, `earnings-revision`, `earnings-forecast`, `management-deep-dive`, `investor-lenses` |
| SEC filing research | `edgar-sec-filings` | `sec-edgar` for retrieval; `financial-statement` for statement analysis |
| Stock screening or watchlists | The exact screen skill | `fundamental-filter`, `sector-rotation`, `breakout-scan`, or `episodic-pivot-scan` according to the requested setup |
| Create or backtest a strategy | `strategy-generate` | The strategy-family skill; `execution-model` for realistic fills; `backtest-diagnose` only after a failed or weak backtest |
| Factor or quantitative research | `factor-research` | `alpha-zoo`, `multi-factor`, `quant-statistics`, `ml-strategy`, `correlation-analysis` |
| Technical analysis | The named technical school | `technical-basic`, `candlestick`, `draw-trendline`, `ichimoku`, `elliott-wave`, `chanlun`, `smc`, or `harmonic` |
| Portfolio, risk, or hedging | The requested portfolio outcome | `asset-allocation`, `risk-analysis`, `hedging-strategy`, `performance-attribution`, `correlation-regime` |
| Options | `options-strategy` | `options-payoff` for scenarios; `options-advanced` for volatility surfaces or dynamic Greeks |
| Crypto market structure | The exact crypto topic | `crypto-derivatives`, `perp-funding-basis`, `liquidation-heatmap`, `onchain-analysis`, `stablecoin-flow`, `token-unlock-treasury`, `defi-yield` |
| Macro, commodities, or credit | The exact top-down topic | `macro-analysis`, `global-macro`, `commodity-analysis`, `credit-analysis`, `geopolitical-risk` |
| Trade history or behavioral review | `trade-journal` | `behavioral-finance`; use `shadow-account` for the full extract-backtest-report loop |
| Long-running, auditable research | `research-goal` | `report-generate` for the final artifact and the relevant domain skill for analysis |
| Read documents or web pages | `doc-reader` or `web-reader` | The domain skill that interprets the retrieved evidence |
| Export a validated strategy | `pine-script` or `vnpy-export` | Load only after the strategy logic and backtest are settled |

## Resolve close matches

- Use `breakout-scan` for sector-led platform breakouts. Use `episodic-pivot-scan` only for gap repricing after a verified material catalyst. Use `event-driven` for designing a broader event-signal strategy.
- Use `sec-edgar` to fetch filing data and `edgar-sec-filings` to interpret filings.
- Use `options-strategy` for construction, `options-payoff` for expiry and scenario P&L, and `options-advanced` for volatility-surface or dynamic-hedging work.
- Use `trade-journal` for diagnostics from an export. Use `shadow-account` when the user wants profitable rules extracted, backtested, and reported.
- Use `macro-analysis` for cycle and policy interpretation. Use `global-macro` when the task connects those views to cross-asset signals or allocation.
- Use `research-goal` for persistence and evidence tracking, not as a substitute for the domain skill.

When two candidates still overlap, compare their live descriptions from `list_skills`. Ask the user only if the choice would materially change the method or deliverable.

## Composition rules

- For investment research, load `research-discipline` before gathering evidence, then load the primary domain skill.
- For any data fetch or backtest, load `data-routing` before selecting a source.
- Let each selected skill own a distinct stage: evidence gathering, analysis, strategy construction, validation, or reporting.
- Load a provider skill only after `data-routing` selects that provider. Do not choose a source merely because its name is familiar.
- Use `list_swarm_presets` and `run_swarm` only when the user requests a team or the task genuinely needs several independent specialist perspectives. A swarm is not a replacement for skill selection.

## Failure and safety behavior

- If `list_skills` or `load_skill` fails, report the exact failure and stop relying on that skill. Do not silently substitute a similarly named workflow.
- Do not fabricate unavailable data, change the requested symbol or market, or hide provider and authentication errors behind an unrelated fallback.
- Preserve dates, symbols, currencies, adjustment modes, and data sources in the final analysis so results are traceable.
- Vibe-Trading's bundled broker tools are for inspection in this plugin. Never claim to place, cancel, or modify a live order.
- Do not create files, update research goals, or invoke paid capabilities unless the user's request authorizes that mutation or cost.

## Examples

**“研究英伟达最近一季财报并估值”**

Load `research-discipline`, then `financial-statement` and `valuation-model`; add `edgar-sec-filings` plus `sec-edgar` when primary filings must be retrieved.

**“找美股 Qullamaggie 突破候选并回测”**

Load `breakout-scan` for candidate selection, then `data-routing` and `strategy-generate` for data and backtesting. Do not replace the requested setup with `episodic-pivot-scan`.

**“分析我的交割单，找出可复现的盈利模式”**

Load `shadow-account` for the complete extraction and validation loop. Use `trade-journal` alone only when the user wants behavioral diagnostics rather than a reconstructed strategy.
