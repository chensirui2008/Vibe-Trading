"""Tests for deterministic U.S. cross-sectional momentum screening."""

from __future__ import annotations

import json

import pandas as pd

from src.tools.momentum_screener_tool import (
    MomentumScreenerTool,
    _classify_upstream_error,
    _default_history_fetcher,
    _download_adjusted_batch,
    _extract_adjusted_frames,
)


def _frame(
    *,
    periods: int = 140,
    end: str = "2026-08-10",
    start_price: float = 100.0,
    end_price: float = 200.0,
) -> pd.DataFrame:
    index = pd.bdate_range(end=end, periods=periods)
    close = [start_price + (end_price - start_price) * offset / (periods - 1) for offset in range(periods)]
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

    payload = json.loads(_tool(frames).execute(as_of="2026-08-10", symbols=["A", "B.US", "C"]))

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
    payload = json.loads(_tool(frames).execute(as_of="2026-08-10", symbols=["FAST", "SLOW"]))
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
        payload = json.loads(tool.execute(as_of="2026-08-10", symbols=["A"], candidate_pct=value))
        assert payload["status"] == "error"
        assert "candidate_pct" in payload["error"]


def test_common_completed_date_prevents_cross_date_comparison() -> None:
    frames = {
        "A.US": _frame(end="2026-08-10", end_price=200),
        "B.US": _frame(end="2026-08-07", end_price=180),
    }
    payload = json.loads(_tool(frames).execute(as_of="2026-08-10", symbols=["A", "B"]))
    assert payload["common_date"] == "2026-08-07"


def test_stale_minority_is_excluded_instead_of_dragging_common_date_backward() -> None:
    frames = {
        "A.US": _frame(end="2026-08-10", end_price=200),
        "B.US": _frame(end="2026-08-10", end_price=180),
        "STALE.US": _frame(end="2026-08-07", end_price=160),
    }
    payload = json.loads(_tool(frames).execute(as_of="2026-08-10", symbols=["A", "B", "STALE"]))
    assert payload["common_date"] == "2026-08-10"
    assert payload["failed_symbols"]["STALE.US"] == "missing_common_date:2026-08-10"
    assert payload["ranked_count"] == 2


def test_duplicate_missing_close_short_history_and_missing_symbol_are_disclosed() -> None:
    frames = {
        "GOOD.US": _frame(),
        "NOCLOSE.US": pd.DataFrame({"open": [1.0] * 140}, index=pd.bdate_range(end="2026-08-10", periods=140)),
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

    tool = MomentumScreenerTool(constituent_loader=lambda: [], history_fetcher=history_fetcher)
    payload = json.loads(tool.execute(as_of="2026-08-10", universe="sp500"))
    assert payload["status"] == "error"
    assert "no fallback universe was used" in payload["error"]
    assert called is False


def test_us_all_loader_metadata_and_symbols_are_forwarded() -> None:
    requested: list[str] = []

    def history_fetcher(symbols, _start, _end):
        requested.extend(symbols)
        return {symbol: _frame() for symbol in symbols}

    tool = MomentumScreenerTool(
        us_universe_loader=lambda: {
            "symbols": ["AAPL", "BIDU"],
            "source": "Eastmoney test directory",
            "source_date": "2026-08-13",
            "raw_instrument_count": 3,
            "excluded_counts": {"unconfirmed_security_type": 1},
        },
        history_fetcher=history_fetcher,
    )
    payload = json.loads(tool.execute(as_of="2026-08-10", universe="us_all"))

    assert payload["status"] == "ok"
    assert requested == ["AAPL.US", "BIDU.US"]
    assert payload["universe"] == "us_all_current_filtered"
    assert payload["constituent_source"] == "Eastmoney test directory"
    assert payload["universe_metadata"]["raw_instrument_count"] == 3


def test_us_all_loader_failure_has_no_sp500_fallback() -> None:
    called = False

    def sp500_loader():
        nonlocal called
        called = True
        return ["AAPL"]

    tool = MomentumScreenerTool(
        constituent_loader=sp500_loader,
        us_universe_loader=lambda: (_ for _ in ()).throw(RuntimeError("page 2 missing")),
    )
    payload = json.loads(tool.execute(as_of="2026-08-10", universe="us_all"))
    assert payload["status"] == "error"
    assert "page 2 missing" in payload["error"]
    assert called is False


def test_invalid_as_of_and_all_missing_history_fail_loudly() -> None:
    tool = _tool({})
    assert json.loads(tool.execute(as_of="2026/08/10", symbols=["A"]))["status"] == "error"
    payload = json.loads(tool.execute(as_of="2026-08-10", symbols=["A"]))
    assert payload["status"] == "error"
    assert payload["failed_symbols"] == {"A.US": "no_history"}


def test_upstream_rate_limit_is_not_mislabeled_as_no_history() -> None:
    tool = MomentumScreenerTool(
        constituent_loader=lambda: [],
        history_fetcher=lambda _symbols, _start, _end: (
            {},
            {"HAE.US": "upstream_rate_limited:yfinance:YFRateLimitError: Too Many Requests"},
        ),
    )
    payload = json.loads(tool.execute(as_of="2026-08-10", symbols=["HAE"]))
    assert payload["status"] == "error"
    assert payload["failed_symbols"]["HAE.US"].startswith("upstream_rate_limited")


def test_parser_failures_are_observable() -> None:
    raw = pd.DataFrame({"Open": [1.0]}, index=pd.DatetimeIndex([pd.Timestamp("2026-08-10")]))
    frames, failures = _extract_adjusted_frames(raw, ["HAE.US"])
    assert frames == {}
    assert failures == {"HAE.US": "missing_adjusted_close"}
    assert _classify_upstream_error("YFRateLimitError: Too Many Requests").startswith("upstream_rate_limited")


def test_download_adapter_returns_call_scoped_yfinance_errors(monkeypatch) -> None:
    import yfinance.multi as yf_multi

    class FakeContext:
        def __init__(self) -> None:
            self.errors = {}

    def fake_impl(context, symbols, **kwargs):
        assert symbols == ["HAE"]
        assert kwargs["auto_adjust"] is True
        context.errors["HAE"] = "YFRateLimitError: Too Many Requests"
        return pd.DataFrame()

    monkeypatch.setattr(yf_multi, "_DownloadCtx", FakeContext)
    monkeypatch.setattr(yf_multi, "_download_impl", fake_impl)
    frame, errors = _download_adjusted_batch(["HAE"], "2026-01-01", "2026-08-11")
    assert frame.empty
    assert errors == {"HAE": "YFRateLimitError: Too Many Requests"}


def test_batch_failures_preserve_earlier_successes(monkeypatch) -> None:
    import src.tools.momentum_screener_tool as module

    success = _frame()
    calls = 0

    def fake_download(symbols, _start, _end):
        nonlocal calls
        calls += 1
        if calls == 1:
            raw = pd.concat({"Close": pd.concat({symbols[0]: success["close"]}, axis=1)}, axis=1)
            return raw, {}
        return pd.DataFrame(), {symbol: "YFRateLimitError: Too Many Requests" for symbol in symbols}

    monkeypatch.setattr(module, "_BATCH_SIZE", 1)
    monkeypatch.setattr(module, "_download_adjusted_batch", fake_download)
    frames, failures = _default_history_fetcher(["GOOD.US", "LIMITED.US"], "2026-01-01", "2026-08-10")

    assert set(frames) == {"GOOD.US"}
    assert failures["LIMITED.US"].startswith("upstream_rate_limited")


def test_empty_batch_without_diagnostics_is_explicit_and_nonfatal(monkeypatch) -> None:
    import src.tools.momentum_screener_tool as module

    monkeypatch.setattr(
        module,
        "_download_adjusted_batch",
        lambda _symbols, _start, _end: (pd.DataFrame(), {}),
    )
    frames, failures = _default_history_fetcher(["HAE.US"], "2026-01-01", "2026-08-10")
    assert frames == {}
    assert failures == {"HAE.US": ("upstream_empty_response:yfinance:empty batch without call-scoped provider errors")}
