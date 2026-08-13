"""Tests for deterministic breakout-base diagnostics."""

from __future__ import annotations

import json

import pandas as pd

from src.tools.breakout_setup_tool import BreakoutSetupTool


def _frame(*, volatile: bool = False) -> pd.DataFrame:
    index = pd.bdate_range(end="2026-08-10", periods=80)
    close = pd.Series([100 + i * 0.4 for i in range(80)], index=index, dtype=float)
    high = close + 1.0
    low = close - 1.0
    volume = pd.Series([1_000_000.0] * 80, index=index)
    if volatile:
        # The fixed base begins at position 40: a 30%+ drawdown followed by a
        # late range expansion must be surfaced as a major contradiction.
        high.iloc[42] = 150.0
        low.iloc[50] = 100.0
        high.iloc[-5:] = [140.0, 145.0, 150.0, 154.0, 158.0]
        low.iloc[-5:] = [115.0, 113.0, 110.0, 106.0, 102.0]
        close.iloc[-5:] = [128.0, 130.0, 132.0, 134.0, 136.0]
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def _tool(frame: pd.DataFrame) -> BreakoutSetupTool:
    return BreakoutSetupTool(history_fetcher=lambda _symbol, _start, _end: (frame, "fixture"))


def test_deep_wide_expanding_base_is_explicitly_contradicted() -> None:
    frame = _frame(volatile=True)
    start = frame.index[40].strftime("%Y-%m-%d")
    payload = json.loads(_tool(frame).execute(symbol="AXON", platform_start=start, as_of="2026-08-10"))

    assert payload["status"] == "ok"
    assert payload["metrics"]["max_drawdown"] < -0.25
    codes = {item["code"] for item in payload["contraindications"]}
    assert "deep_base_drawdown" in codes
    assert "very_wide_base" in codes
    assert "recent_volatility_expansion" in codes
    assert payload["structure_assessment"] == "contradicted"


def test_fixed_window_and_metrics_are_reported_without_binary_strategy_grade() -> None:
    frame = _frame()
    start = frame.index[40].strftime("%Y-%m-%d")
    payload = json.loads(_tool(frame).execute(symbol="TEST.US", platform_start=start, as_of="2026-08-10"))

    assert payload["platform_start"] == start
    assert payload["source"] == "fixture"
    assert payload["base_bars"] == 40
    assert "ideal_references" in payload
    assert "final_grade" not in payload


def test_invalid_dates_and_missing_ohlcv_fail_loudly() -> None:
    tool = _tool(pd.DataFrame())
    payload = json.loads(tool.execute(symbol="AAPL", platform_start="2026-08-11", as_of="2026-08-10"))
    assert payload["status"] == "error"
    assert "after as_of" in payload["error"]
