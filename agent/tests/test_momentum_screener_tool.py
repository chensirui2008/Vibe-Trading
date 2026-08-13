"""Tests for deterministic U.S. cross-sectional momentum screening."""

from __future__ import annotations

import json

import pandas as pd

from src.tools.momentum_screener_tool import MomentumScreenerTool


def _frame(
    *,
    periods: int = 140,
    end: str = "2026-08-10",
    start_price: float = 100.0,
    end_price: float = 200.0,
) -> pd.DataFrame:
    index = pd.bdate_range(end=end, periods=periods)
    close = [
        start_price + (end_price - start_price) * offset / (periods - 1)
        for offset in range(periods)
    ]
    return pd.DataFrame({"close": close}, index=index)


def _tool(frames: dict[str, pd.DataFrame], constituents=None) -> MomentumScreenerTool:
    return MomentumScreenerTool(
        constituent_loader=lambda: constituents or [],
        history_fetcher=lambda _symbols, _start, _end: frames,
    )


def test_returns_ranks_ties_and_top_two_union() -> None:
    index = pd.bdate_range(end="2026-08-10", periods=140)
    frames = {}
    # A and B tie on all horizons. C is weaker. With three names the minimum
    # top bucket is one rank, and rank(method=min) keeps both tied leaders.
    for symbol, finish in (("A.US", 200.0), ("B.US", 200.0), ("C.US", 120.0)):
        values = [100.0 + (finish - 100.0) * i / 139 for i in range(140)]
        frames[symbol] = pd.DataFrame({"close": values}, index=index)

    payload = json.loads(
        _tool(frames).execute(
            as_of="2026-08-10", symbols=["A", "B.US", "C"]
        )
    )

    assert payload["status"] == "ok"
    rows = {row["symbol"]: row for row in payload["candidates"]}
    assert set(rows) == {"A.US", "B.US"}
    assert rows["A.US"]["r21_rank"] == rows["B.US"]["r21_rank"] == 1
    assert rows["A.US"]["r21_denominator"] == 3
    assert rows["A.US"]["core_periods"] == 3


def test_small_custom_universe_keeps_first_for_each_horizon() -> None:
    frames = {
        "FAST.US": _frame(end_price=240),
        "SLOW.US": _frame(end_price=110),
    }
    payload = json.loads(
        _tool(frames).execute(
            as_of="2026-08-10", symbols=["FAST", "SLOW"]
        )
    )
    assert [row["symbol"] for row in payload["candidates"]] == ["FAST.US"]
    assert payload["candidates"][0]["r126_rank"] == 1


def test_wider_candidate_pool_keeps_top_one_and_two_labels() -> None:
    index = pd.bdate_range(end="2026-08-10", periods=140)
    frames = {}
    for rank in range(1, 21):
        finish = 220.0 - rank
        values = [100.0 + (finish - 100.0) * i / 139 for i in range(140)]
        frames[f"S{rank:02d}.US"] = pd.DataFrame({"close": values}, index=index)

    payload = json.loads(
        _tool(frames).execute(
            as_of="2026-08-10",
            symbols=[f"S{rank:02d}" for rank in range(1, 21)],
            candidate_pct=10,
        )
    )

    assert payload["candidate_pct"] == 10
    assert [row["symbol"] for row in payload["candidates"]] == [
        "S01.US",
        "S02.US",
    ]
    assert payload["candidates"][0]["bucket"] == "core"
    assert payload["candidates"][1]["bucket"] == "broad"


def test_candidate_percentage_is_bounded() -> None:
    tool = _tool({})
    for value in (0, 21, 2.5, True):
        payload = json.loads(
            tool.execute(as_of="2026-08-10", symbols=["A"], candidate_pct=value)
        )
        assert payload["status"] == "error"
        assert "candidate_pct" in payload["error"]


def test_common_completed_date_prevents_cross_date_comparison() -> None:
    frames = {
        "A.US": _frame(end="2026-08-10", end_price=200),
        "B.US": _frame(end="2026-08-07", end_price=180),
    }
    payload = json.loads(
        _tool(frames).execute(as_of="2026-08-10", symbols=["A", "B"])
    )
    assert payload["common_date"] == "2026-08-07"


def test_duplicate_missing_close_short_history_and_missing_symbol_are_disclosed() -> None:
    frames = {
        "GOOD.US": _frame(),
        "NOCLOSE.US": pd.DataFrame(
            {"open": [1.0] * 140}, index=pd.bdate_range(end="2026-08-10", periods=140)
        ),
        "SHORT.US": _frame(periods=50),
    }
    payload = json.loads(
        _tool(frames).execute(
            as_of="2026-08-10",
            symbols=["GOOD", "good.us", "NOCLOSE", "SHORT", "MISSING", "bad symbol"],
        )
    )
    assert payload["duplicate_symbols"] == ["GOOD.US"]
    assert payload["failed_symbols"]["NOCLOSE.US"] == "missing_close"
    assert payload["failed_symbols"]["SHORT.US"].startswith("insufficient_history:")
    assert payload["failed_symbols"]["MISSING.US"] == "no_history"
    assert payload["failed_symbols"]["bad symbol"] == "invalid_symbol"


def test_empty_sp500_roster_fails_without_fallback_or_history_call() -> None:
    called = False

    def history_fetcher(_symbols, _start, _end):
        nonlocal called
        called = True
        return {}

    tool = MomentumScreenerTool(
        constituent_loader=lambda: [], history_fetcher=history_fetcher
    )
    payload = json.loads(tool.execute(as_of="2026-08-10", universe="sp500"))
    assert payload["status"] == "error"
    assert "no fallback universe was used" in payload["error"]
    assert called is False


def test_invalid_as_of_and_all_missing_history_fail_loudly() -> None:
    tool = _tool({})
    assert json.loads(tool.execute(as_of="2026/08/10", symbols=["A"]))["status"] == "error"
    payload = json.loads(tool.execute(as_of="2026-08-10", symbols=["A"]))
    assert payload["status"] == "error"
    assert payload["failed_symbols"] == {"A.US": "no_history"}
