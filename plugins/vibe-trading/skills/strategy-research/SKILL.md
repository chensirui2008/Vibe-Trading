---
name: strategy-research
description: Research, specify, and validate an original U.S.-equity trading strategy end to end, from web and academic evidence through a reproducible Vibe-Trading backtest, then produce a feasibility report and an operational playbook. Use for deep strategy-research requests, not for a quick canned-strategy backtest or non-U.S. markets.
---

# Strategy Research

Build a falsifiable U.S.-equity strategy from first principles and test whether the evidence survives realistic historical validation. The required deliverables are a strategy feasibility report and a detailed strategy playbook.

Use Vibe-Trading's catalog and tools throughout the workflow. Call `list_skills` first, then use `load_skill` for relevant supporting capabilities such as research discipline, literature or document analysis, data routing, factor research, technical analysis, fundamentals, execution modeling, backtest diagnosis, research goals, and report generation.

Do not load or follow a skill whose primary purpose is to provide a complete ready-made trading strategy, a complete set of entry/exit/sizing rules, or a strategy template that substitutes for original construction in this workflow. This restriction applies to complete-strategy skills only; it does not exclude analytical methods, indicators, factors, data-provider guidance, validation methods, execution assumptions, or reporting support. Use the live skill descriptions to judge the boundary. If a loaded supporting skill recommends a complete-strategy skill, do not follow that recommendation.

## Scope and intake

Support U.S.-listed equities and U.S. equity ETFs only. If the request concerns another market or asset class, say that this skill is U.S.-equity-specific and ask whether to adapt the request before continuing.

Before research, establish the decisions that would materially change the test:

- research question or observed anomaly;
- eligible security universe and point-in-time membership rule;
- daily or intraday bar frequency, intended holding period, and rebalance cadence;
- long-only or long/short mandate, benchmark, capital, leverage, and position limits;
- backtest window and the final untouched out-of-sample period;
- transaction-cost, slippage, liquidity, tax, and short-borrow assumptions;
- required implementation environment and any user-specific constraints.

Ask for missing material choices. For unspecified secondary choices, state conservative initial assumptions and keep them visible throughout the report. Resolve ambiguous names with `search_symbol`; use the `.US` convention for U.S. tickers in market-data calls.

## Vibe-Trading tools

Prefer these bundled tools and inspect their live schemas before calling them:

| Stage | Tools | Use |
| --- | --- | --- |
| Supporting skill discovery | `list_skills`, `load_skill` | Discover and load useful non-complete-strategy skills; never load a ready-made complete-strategy skill. |
| Web evidence | `web_search`, `read_url` | Discover sources, then read the actual source rather than relying on snippets. |
| Academic evidence | `research_papers` | Search arXiv/OpenAlex, read selected records, and separate paper claims from reproduced results. |
| Symbol and price data | `search_symbol`, `get_market_data` | Resolve tickers and fetch complete OHLCV. For research samples use explicit dates, `interval="1D"`, and `max_rows=0`. |
| Point-in-time company data | `get_fundamentals`, `get_sec_filings` | Use filed-date-aligned fundamentals and primary SEC evidence when the signal requires them. |
| Context only | `get_stock_profile`, `get_stock_news`, `get_sector_info`, `get_macro_series` | Explain mechanisms or regimes; do not leak later information into historical signals. |
| Implementation artifacts | `write_file`, `read_file` | Create and inspect the run's `config.json` and `code/signal_engine.py` in an allowed research run directory. |
| Validation | `backtest`, optionally `factor_analysis` | Execute the frozen strategy and analyze cross-sectional factor predictiveness when applicable. |
| Auditable long runs | `start_research_goal`, `add_goal_evidence`, `update_research_goal_status` | Use only when the user requests persistent or auditable goal tracking. |
| Premium data | `qveris_search`, `qveris_inspect`, `qveris_execute` | Discovery and inspection are prerequisites; execute only after explicit approval of the expected paid call. |

Do not substitute a different symbol, field, source, or date range when a tool fails. Surface the exact failure and either correct the root cause or mark the affected claim untested. Never use broker tools or place trades in this workflow.

## Workflow

### 1. Freeze the research protocol

Write down, before seeing performance, the economic or behavioral mechanism, the falsifiable prediction, primary metric, benchmark, test universe, timing convention, parameter ranges, and rejection criteria. Define what result would make the strategy infeasible. Separate a hypothesis inspired by evidence from a rule copied after observing returns.

Use chronological partitions:

- an in-sample period for formulation and limited calibration;
- a validation period for choosing among predeclared alternatives;
- a final untouched out-of-sample period for the feasibility decision.

When the available history permits it, add walk-forward evaluation. Never random-shuffle time-series observations for the main test.

### 2. Research the mechanism and prior evidence

Search the web and academic literature with several queries covering the proposed mechanism, contrary evidence, implementation costs, and known failure regimes. Prefer original papers, regulator or exchange material, SEC filings, official datasets, and first-party methodology documents. Use secondary commentary only to locate or contextualize primary evidence.

For every material source, record title, publisher or author, publication date, URL or paper id, evidence date, exact claim supported, market/sample, and limitations. Treat abstracts, backtests in papers, and marketing results as claims to reproduce—not as proof of feasibility. Actively search for disconfirming evidence and plausible alternative explanations.

End this stage with a mechanism map:

1. cause or market friction;
2. observable proxy available at decision time;
3. expected return path and holding horizon;
4. why competition should not immediately eliminate it;
5. conditions under which it should weaken or reverse.

If the mechanism cannot produce a measurable, time-stamped signal, stop and report insufficient specification rather than inventing one.

### 3. Specify the strategy completely

Convert the hypothesis into deterministic rules before the main backtest. Specify:

- point-in-time universe construction, exclusions, delisting treatment, and membership refresh;
- every input field, provider, adjustment convention, publication lag, timezone, and missing-value rule;
- signal formula with parameter units and lookback windows;
- decision timestamp and earliest legal fill timestamp;
- entry, add, reduce, exit, stop, time-stop, and re-entry rules;
- ranking and tie-breaking for competing candidates;
- position-sizing formula, portfolio caps, cash rule, leverage, and exposure limits;
- fill model, commissions, spread/slippage, liquidity participation, and short-borrow assumptions;
- benchmark and rebalance convention.

Include equations or precise pseudocode. A reader must be able to implement the same target positions without discretionary interpretation. Indicators computed using bar `t` data cannot receive a fill earlier than the next executable price unless the data is demonstrably available before that fill.

### 4. Audit data before testing

Fetch the full required OHLCV range with `get_market_data` and `max_rows=0`; inspect returned source metadata, unresolved symbols, gaps, duplicates, timezone, corporate-action adjustment, and coverage. For fundamental signals, use `get_fundamentals` with point-in-time alignment and explicit filing lags. Do not use the current S&P 500 membership as a historical universe without identifying the survivorship bias.

Document unavailable data and resulting bias. Fail closed on unresolved symbols, truncated histories, future-dated fundamentals, or inconsistent calendars. Do not silently forward-fill event or fundamental fields across periods where availability is unknown.

### 5. Implement a reproducible run

Create a dedicated allowed run directory containing:

- `config.json` with U.S. `.US` codes, explicit start/end dates, `source="yfinance"` or another justified source, `interval="1D"`, `engine="daily"`, initial cash, benchmark, and validation assumptions;
- `code/signal_engine.py` defining `SignalEngine.generate(data_map)` and returning target-position series aligned to each symbol's bars.

Keep signal code deterministic and side-effect free. Encode only the frozen rules. Record the config, code path, data as-of date, and any parameter set used. Call `backtest` on the run directory and preserve its returned metrics and artifact paths. If execution fails, diagnose the actual schema, data, path, or signal-contract error; do not weaken the test or insert a fallback strategy.

### 6. Validate rather than optimize

Report in-sample, validation, and untouched out-of-sample results separately. At minimum compare against the declared benchmark and a simple exposure-matched baseline. Evaluate:

- total and annualized return, volatility, Sharpe, Sortino, maximum drawdown, Calmar, and time underwater;
- alpha/excess return and beta where available;
- number of trades, hit rate, payoff ratio, average holding period, exposure, turnover, and concentration;
- gross versus net performance and sensitivity to higher costs/slippage;
- performance by subperiod, market regime, sector, market-cap/liquidity bucket, and long/short leg when relevant.

Run robustness checks suited to the design: broad parameter neighborhoods, delayed entry, alternative executable prices, doubled costs, shorter history windows, leave-one-symbol/sector-out tests, walk-forward windows, and plausible universe variants. Treat isolated parameter peaks, dependence on a few names or dates, low trade counts, or collapse after costs as evidence against feasibility.

Do not tune on the final out-of-sample period. Count materially tried variants and discuss data-snooping risk. A successful full-period equity curve cannot override failed out-of-sample or leakage checks.

### 7. Make the feasibility decision

Use one of four verdicts:

- **可行**: the predeclared core hypothesis survives out-of-sample, costs, and relevant robustness checks with implementable data and execution;
- **有条件可行**: evidence is positive but depends on explicit capacity, regime, data, or operational conditions;
- **不可行**: the hypothesis fails the rejection criteria, realistic costs, or robustness tests;
- **证据不足**: missing point-in-time data, insufficient history/trades, unresolved leakage, or failed tooling prevents a valid decision.

Do not upgrade the verdict because the strategy is intuitively appealing. State uncertainty, contradictory evidence, and the strongest reason the conclusion could be wrong.

## Required deliverables

Return both artifacts in the user's language. Cite source URLs or paper identifiers beside the claims they support, and distinguish literature claims from this run's observed results.

### Strategy feasibility report

1. Verdict and one-paragraph decision rationale.
2. Research scope, data as-of date, universe, benchmark, and frozen assumptions.
3. Mechanism, falsifiable hypothesis, supporting and contrary evidence.
4. Complete strategy specification and signal timing.
5. Data provenance and quality/bias audit.
6. Backtest protocol, run directory, configuration, costs, and partition dates.
7. In-sample, validation, and out-of-sample results in a comparable table.
8. Robustness, sensitivity, regime, concentration, and falsification results.
9. Failure modes, implementation constraints, capacity, and unresolved limitations.
10. Final verdict, confidence level, and the next test that could change it.

### Detailed strategy playbook

1. Strategy objective and the mechanism it is exploiting.
2. Eligible universe, required data, scan schedule, and setup filters.
3. Exact signal formula and pre-trade checklist.
4. Entry timing, order assumption, ranking, and tie-break rules.
5. Position sizing with formula, portfolio construction, and exposure caps.
6. Exit, stop, time-stop, re-entry, and conflict-resolution rules.
7. Transaction-cost, liquidity, borrow, and capacity constraints.
8. Daily/weekly monitoring fields and data-quality alerts.
9. Disable conditions, drawdown or regime kill criteria, and escalation steps.
10. Review cadence, recalibration boundaries, recordkeeping, and one worked example.

End with a traceability block listing every material assumption, source, tool used, data date, run/artifact path, known failure, and any section that remains unverified. Present the work as research, not personalized financial advice or a promise of future returns.
