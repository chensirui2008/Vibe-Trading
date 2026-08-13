"""Tests for deterministic breakout-base diagnostics."""

from __future__ import annotations

import json

import pandas as pd

from src.tools.breakout_setup_tool import BreakoutSetupTool, _resistance_zone


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


def test_platform_resistance_zone_excludes_evaluation_bar_and_confirms_on_close() -> None:
    frame = _frame()
    start_position = 60
    start = frame.index[start_position].strftime("%Y-%m-%d")
    frame.loc[frame.index[start_position]:, "high"] = [130.0, 128.0, 129.0, 127.0, 126.0] * 4
    frame.loc[frame.index[start_position]:, "low"] = [120.0 + index * 0.2 for index in range(20)]
    frame.loc[frame.index[-1], ["open", "high", "low", "close"]] = [130.0, 134.0, 129.0, 133.0]

    payload = json.loads(_tool(frame).execute(symbol="TEST", platform_start=start, as_of="2026-08-10"))

    zone = payload["resistance_zone"]
    assert zone["touch_count"] >= 2
    assert zone["upper"] == 130.0
    assert all(touch["date"] != "2026-08-10" for touch in zone["touches"])
    assert payload["breakout"]["close_above_upper"] is True
    assert payload["breakout"]["intraday_test_above_upper"] is True


def test_intraday_zone_test_is_not_a_confirmed_breakout() -> None:
    frame = _frame()
    start_position = 60
    start = frame.index[start_position].strftime("%Y-%m-%d")
    frame.loc[frame.index[start_position]:, "high"] = [130.0, 128.0, 129.0, 127.0, 126.0] * 4
    frame.loc[frame.index[-1], ["open", "high", "low", "close"]] = [129.0, 134.0, 127.0, 129.5]

    payload = json.loads(_tool(frame).execute(symbol="TEST", platform_start=start, as_of="2026-08-10"))

    assert payload["breakout"]["intraday_test_above_upper"] is True
    assert payload["breakout"]["close_above_upper"] is False


def test_resistance_zone_ignores_dense_middle_prices_below_top_quartile() -> None:
    index = pd.bdate_range("2026-07-01", periods=12)
    highs = pd.Series(
        [100.0, 100.2, 99.9, 100.1, 100.0, 100.2, 99.8, 100.1, 110.0, 109.0, 110.5, 108.5],
        index=index,
    )

    zone = _resistance_zone(highs)

    assert zone is not None
    assert zone["lower"] == 109.0
    assert zone["upper"] == 110.5
    assert zone["touch_count"] == 3


def test_single_upper_extreme_does_not_create_a_resistance_zone() -> None:
    index = pd.bdate_range("2026-07-01", periods=8)
    highs = pd.Series([100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 110.0], index=index)

    assert _resistance_zone(highs) is None


def test_higher_lows_compare_formation_half_minima_without_pivots() -> None:
    frame = _frame()
    start_position = 60
    start = frame.index[start_position].strftime("%Y-%m-%d")
    frame.loc[frame.index[start_position:start_position + 9], "low"] = 100.0
    frame.loc[frame.index[start_position + 9:-1], "low"] = 105.0

    payload = json.loads(_tool(frame).execute(symbol="TEST", platform_start=start, as_of="2026-08-10"))

    assert payload["low_structure"]["method"] == "second_half_min_low_above_first_half_min_low"
    assert payload["low_structure"]["first_half_min_low"] == 100.0
    assert payload["low_structure"]["second_half_min_low"] == 105.0
    assert payload["higher_lows"] is True
    assert "confirmed_pivot" not in payload
