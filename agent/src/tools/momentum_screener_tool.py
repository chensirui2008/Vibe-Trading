"""Deterministic cross-sectional momentum screening for U.S. equities."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

import pandas as pd

from src.agent.tools import BaseTool

_HORIZONS = (21, 63, 126)
_MIN_BARS = max(_HORIZONS) + 1
_FETCH_CALENDAR_DAYS = 220
_BATCH_SIZE = 100


def _error(message: str, **details: Any) -> str:
    return json.dumps(
        {"status": "error", "error": message, **details},
        ensure_ascii=False,
        allow_nan=False,
    )


def _normalize_symbol(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    if symbol.endswith(".US"):
        symbol = symbol[:-3]
    symbol = symbol.replace(".", "-")
    if not symbol or not all(ch.isalnum() or ch in {"-", "_"} for ch in symbol):
        return None
    return f"{symbol}.US"


def _default_constituent_loader() -> list[str]:
    # Reuse the current-roster reader, but deliberately not its hand-picked
    # fallback: a failed S&P 500 roster fetch must remain visible.
    from src.tools.alpha_bench_tool import _fetch_sp500_constituents

    return _fetch_sp500_constituents()


def _default_us_universe_loader() -> Mapping[str, Any]:
    from src.tools.market_screener_tool import _load_us_equity_universe

    return _load_us_equity_universe()


def _extract_adjusted_frames(
    raw: pd.DataFrame, symbols: Sequence[str]
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Split one yfinance batch into project-symbol adjusted-close frames."""
    if raw is None or raw.empty:
        return {}, {}
    yahoo_symbols = [symbol[:-3] for symbol in symbols]
    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for project_symbol, yahoo_symbol in zip(symbols, yahoo_symbols):
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                selected = None
                for level in range(raw.columns.nlevels):
                    if yahoo_symbol in raw.columns.get_level_values(level):
                        selected = raw.xs(yahoo_symbol, axis=1, level=level, drop_level=True)
                        break
                if selected is None:
                    failures[project_symbol] = "symbol_missing_from_batch_response"
                    continue
            elif len(symbols) == 1:
                selected = raw
            else:
                failures[project_symbol] = "ambiguous_non_multiindex_batch_response"
                continue
            close_col = next(
                (column for column in selected.columns if str(column).lower() == "close"),
                None,
            )
            if close_col is None:
                failures[project_symbol] = "missing_adjusted_close"
                continue
            close = pd.to_numeric(selected[close_col], errors="coerce").dropna()
            index = pd.DatetimeIndex(pd.to_datetime(close.index))
            if index.tz is not None:
                index = index.tz_localize(None)
            frame = pd.DataFrame({"close": close.to_numpy()}, index=index.normalize())
            frame = frame[~frame.index.duplicated(keep="last")].sort_index()
            frame = frame[frame["close"] > 0]
            if not frame.empty:
                frames[project_symbol] = frame
            else:
                failures[project_symbol] = "no_usable_adjusted_close"
        except Exception as exc:
            failures[project_symbol] = f"parse_error:{type(exc).__name__}:{exc}"
    return frames, failures


def _default_history_fetcher(
    symbols: Sequence[str], start_date: str, end_date: str
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Fetch split/dividend-adjusted daily closes in bounded batches."""
    fetched: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    exclusive_end = (pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    for offset in range(0, len(symbols), _BATCH_SIZE):
        batch = list(symbols[offset : offset + _BATCH_SIZE])
        yahoo_batch = [symbol[:-3] for symbol in batch]
        try:
            raw, call_errors = _download_adjusted_batch(yahoo_batch, start_date, exclusive_end)
        except Exception as exc:
            detail = " ".join(str(exc).split())[:300]
            for symbol in batch:
                failures[symbol] = f"batch_request_error:yfinance:{type(exc).__name__}:{detail}"
            continue

        for project_symbol, yahoo_symbol in zip(batch, yahoo_batch):
            detail = call_errors.get(yahoo_symbol)
            if detail:
                failures[project_symbol] = _classify_upstream_error(str(detail))

        parsed, parse_failures = _extract_adjusted_frames(raw, batch)
        fetched.update(parsed)
        for symbol in parsed:
            failures.pop(symbol, None)
        for symbol, reason in parse_failures.items():
            failures.setdefault(symbol, reason)
        if raw is None or raw.empty:
            unresolved = [symbol for symbol in batch if symbol not in failures]
            for symbol in unresolved:
                failures[symbol] = "upstream_empty_response:yfinance:empty batch without call-scoped provider errors"
    return fetched, failures


def _download_adjusted_batch(
    yahoo_symbols: Sequence[str], start_date: str, exclusive_end: str
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Run one yfinance download and return its call-scoped error map.

    yfinance 1.5 moved failures from ``shared._ERRORS`` into a private
    per-invocation ``_DownloadCtx``. The public ``download`` API discards that
    context, so using it would make rate limits indistinguishable from a truly
    empty response. Fail loudly if this versioned adapter disappears instead
    of silently returning misleading ``no_history`` results.
    """
    from yfinance import multi as yf_multi

    context_type = getattr(yf_multi, "_DownloadCtx", None)
    download_impl = getattr(yf_multi, "_download_impl", None)
    if context_type is None or download_impl is None:
        raise RuntimeError("installed yfinance does not expose call-scoped download diagnostics")
    context = context_type()
    raw = download_impl(
        context,
        list(yahoo_symbols),
        start=start_date,
        end=exclusive_end,
        interval="1d",
        auto_adjust=True,
        actions=False,
        progress=False,
        threads=True,
    )
    return raw, dict(context.errors)


def _classify_upstream_error(detail: str) -> str:
    lowered = detail.lower()
    if "ratelimit" in lowered or "too many requests" in lowered or "429" in lowered:
        code = "upstream_rate_limited"
    elif "possibly delisted" in lowered or "no price data found" in lowered:
        code = "upstream_no_price_data"
    else:
        code = "upstream_error"
    compact = " ".join(detail.split())
    return f"{code}:yfinance:{compact[:300]}"


def _rank_rows(returns: pd.DataFrame, *, candidate_pct: int = 2) -> list[dict[str, Any]]:
    metrics: dict[int, pd.DataFrame] = {}
    selected: set[str] = set()
    for horizon in _HORIZONS:
        column = f"r{horizon}"
        valid = returns[[column]].dropna().copy()
        valid["rank"] = valid[column].rank(method="min", ascending=False).astype(int)
        denominator = len(valid)
        valid["denominator"] = denominator
        valid["top_pct"] = valid["rank"] / denominator * 100.0
        valid["top_1"] = valid["rank"] <= max(1, math.ceil(denominator * 0.01))
        valid["top_2"] = valid["rank"] <= max(1, math.ceil(denominator * 0.02))
        valid["selected"] = valid["rank"] <= max(1, math.ceil(denominator * candidate_pct / 100.0))
        metrics[horizon] = valid
        selected.update(valid.index[valid["selected"]])

    rows: list[dict[str, Any]] = []
    for symbol in selected:
        row: dict[str, Any] = {
            "symbol": symbol,
            "core_periods": 0,
            "preferred_periods": 0,
        }
        best_pct = float("inf")
        for horizon in _HORIZONS:
            metric = metrics[horizon]
            prefix = f"r{horizon}"
            if symbol not in metric.index:
                row[prefix] = None
                row[f"{prefix}_rank"] = None
                row[f"{prefix}_denominator"] = len(metric)
                row[f"{prefix}_top_pct"] = None
                continue
            item = metric.loc[symbol]
            top_pct = float(item["top_pct"])
            row[prefix] = float(item[prefix])
            row[f"{prefix}_rank"] = int(item["rank"])
            row[f"{prefix}_denominator"] = int(item["denominator"])
            row[f"{prefix}_top_pct"] = top_pct
            row["core_periods"] += int(bool(item["top_1"]))
            row["preferred_periods"] += int(bool(item["top_2"]))
            best_pct = min(best_pct, top_pct)
        if row["core_periods"]:
            row["bucket"] = "core"
        elif row["preferred_periods"]:
            row["bucket"] = "watch"
        else:
            row["bucket"] = "broad"
        row["best_top_pct"] = best_pct
        rows.append(row)
    rows.sort(
        key=lambda row: (
            -row["core_periods"],
            -row["preferred_periods"],
            row["best_top_pct"],
            row["symbol"],
        )
    )
    return rows


class MomentumScreenerTool(BaseTool):
    """Rank 21/63/126-session returns in a broad or custom U.S. universe."""

    name = "screen_momentum"
    description = (
        "Read-only U.S. equity momentum screen. Resolves a current broad U.S. "
        "market universe, the current S&P 500 proxy, or an explicit symbol "
        "list; fetches adjusted daily closes in "
        "batches, and returns the union of each horizon's configurable top "
        "percentage for 21, 63, and 126 sessions with ranks, denominators, "
        "coverage, and failures. Top 1% and 2% labels are always retained. "
        "Requires an explicit as_of date. It does not detect chart bases or pivots."
    )
    parameters = {
        "type": "object",
        "properties": {
            "as_of": {
                "type": "string",
                "description": "Inclusive data cutoff in YYYY-MM-DD format.",
            },
            "universe": {
                "type": "string",
                "enum": ["us_all", "sp500"],
                "default": "us_all",
                "description": "Broad current U.S. equities or current-constituent S&P 500 proxy.",
            },
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional U.S. symbols such as AAPL or AAPL.US. When supplied, "
                    "this custom universe replaces the named universe."
                ),
            },
            "candidate_pct": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 2,
                "description": (
                    "Return the union of names inside this top percentage in "
                    "any horizon. Top 1% and 2% labels remain unchanged."
                ),
            },
        },
        "required": ["as_of"],
        "additionalProperties": False,
    }
    repeatable = True
    is_readonly = True

    def __init__(
        self,
        *,
        constituent_loader: Callable[[], Sequence[str]] | None = None,
        us_universe_loader: Callable[[], Mapping[str, Any]] | None = None,
        history_fetcher: Callable[
            [Sequence[str], str, str],
            Mapping[str, pd.DataFrame] | tuple[Mapping[str, pd.DataFrame], Mapping[str, str]],
        ]
        | None = None,
    ) -> None:
        self._constituent_loader = constituent_loader or _default_constituent_loader
        self._us_universe_loader = us_universe_loader or _default_us_universe_loader
        self._history_fetcher = history_fetcher or _default_history_fetcher

    def execute(self, **kwargs: Any) -> str:
        candidate_pct = kwargs.get("candidate_pct", 2)
        if isinstance(candidate_pct, bool) or not isinstance(candidate_pct, int) or not 1 <= candidate_pct <= 20:
            return _error("candidate_pct must be an integer from 1 to 20")

        raw_as_of = kwargs.get("as_of")
        try:
            as_of = pd.Timestamp(raw_as_of).normalize()
        except Exception:
            return _error("as_of must be a valid YYYY-MM-DD date")
        if not isinstance(raw_as_of, str) or as_of.strftime("%Y-%m-%d") != raw_as_of:
            return _error("as_of must use YYYY-MM-DD format")
        if as_of.date() > date.today():
            return _error("as_of cannot be in the future")

        raw_symbols = kwargs.get("symbols")
        universe_metadata: dict[str, Any] = {}
        duplicate_symbols: list[str] = []
        invalid_symbols: list[str] = []
        if raw_symbols is not None:
            if not isinstance(raw_symbols, list) or not raw_symbols:
                return _error("symbols must be a non-empty array when supplied")
            symbols: list[str] = []
            seen: set[str] = set()
            for raw in raw_symbols:
                symbol = _normalize_symbol(raw)
                if symbol is None:
                    invalid_symbols.append(str(raw))
                    continue
                if symbol in seen:
                    duplicate_symbols.append(symbol)
                    continue
                seen.add(symbol)
                symbols.append(symbol)
            universe_name = "custom"
            constituent_source = "user-supplied"
            constituent_date = None
            survivorship_bias = None
        else:
            universe = kwargs.get("universe", "us_all")
            if universe not in {"us_all", "sp500"}:
                return _error("universe must be 'us_all' or 'sp500'")
            try:
                if universe == "us_all":
                    universe_metadata = dict(self._us_universe_loader())
                    raw_constituents = list(universe_metadata.pop("symbols", []) or [])
                else:
                    raw_constituents = list(self._constituent_loader())
            except Exception as exc:
                return _error(f"{universe} constituent load failed: {exc}")
            if not raw_constituents:
                return _error(f"{universe} constituent load returned no symbols; no fallback universe was used")
            symbols = []
            seen = set()
            for raw in raw_constituents:
                symbol = _normalize_symbol(raw)
                if symbol is None:
                    invalid_symbols.append(str(raw))
                    continue
                if symbol in seen:
                    duplicate_symbols.append(symbol)
                    continue
                seen.add(symbol)
                symbols.append(symbol)
            universe_name = "us_all_current_filtered" if universe == "us_all" else "sp500_current_proxy"
            constituent_source = (
                universe_metadata.get("source")
                if universe == "us_all"
                else "wikipedia current S&P 500 constituents"
            )
            constituent_date = (
                universe_metadata.get("source_date") if universe == "us_all" else date.today().isoformat()
            )
            survivorship_bias = True

        if not symbols:
            return _error("no valid U.S. symbols remained after normalization")

        # Today's daily bar can be incomplete. Stop at the previous calendar
        # day and let the data identify the latest completed trading session.
        requested_end = as_of - pd.Timedelta(days=1) if as_of.date() == date.today() else as_of
        start = requested_end - pd.Timedelta(days=_FETCH_CALENDAR_DAYS)
        try:
            fetch_result = self._history_fetcher(
                symbols,
                start.strftime("%Y-%m-%d"),
                requested_end.strftime("%Y-%m-%d"),
            )
            if isinstance(fetch_result, tuple):
                fetched = dict(fetch_result[0])
                upstream_failures = dict(fetch_result[1])
            else:
                fetched = dict(fetch_result)
                upstream_failures = {}
        except Exception as exc:
            return _error(f"adjusted history batch failed: {exc}")

        cleaned: dict[str, pd.DataFrame] = {}
        failed_reasons: dict[str, str] = {value: "invalid_symbol" for value in invalid_symbols}
        failed_reasons.update(upstream_failures)
        for symbol in symbols:
            frame = fetched.get(symbol)
            if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
                failed_reasons.setdefault(symbol, "no_history")
                continue
            if "close" not in frame.columns:
                failed_reasons[symbol] = "missing_close"
                continue
            series = pd.to_numeric(frame["close"], errors="coerce")
            index = pd.DatetimeIndex(pd.to_datetime(frame.index))
            if index.tz is not None:
                index = index.tz_localize(None)
            normalized = pd.DataFrame({"close": series.to_numpy()}, index=index.normalize())
            normalized = normalized[~normalized.index.duplicated(keep="last")].sort_index()
            normalized = normalized[(normalized.index <= requested_end) & (normalized["close"] > 0)]
            if normalized.empty:
                failed_reasons[symbol] = "no_usable_adjusted_close"
                continue
            if len(normalized) < _MIN_BARS:
                failed_reasons[symbol] = f"insufficient_history:{len(normalized)}/{_MIN_BARS}"
                continue
            cleaned[symbol] = normalized

        if not cleaned:
            return _error(
                "no symbol returned usable adjusted history",
                failed_symbols=failed_reasons,
            )

        date_counts: dict[pd.Timestamp, int] = {}
        for frame in cleaned.values():
            for trading_date in frame.index:
                date_counts[trading_date] = date_counts.get(trading_date, 0) + 1
        if not date_counts:
            return _error(
                "symbols have no common completed trading date",
                failed_symbols=failed_reasons,
            )
        # Use the latest date supported by a strict majority. This preserves a
        # shared date for a two-name custom set, while preventing a small stale
        # or halted minority from dragging a market-wide screen backward.
        minimum_coverage = len(cleaned) // 2 + 1
        common_date = max(
            trading_date
            for trading_date, coverage in date_counts.items()
            if coverage >= minimum_coverage
        )

        returns_rows: dict[str, dict[str, float]] = {}
        for symbol, frame in cleaned.items():
            if common_date not in frame.index:
                failed_reasons[symbol] = f"missing_common_date:{common_date.date().isoformat()}"
                continue
            history = frame.loc[frame.index <= common_date, "close"]
            if len(history) < _MIN_BARS:
                failed_reasons[symbol] = f"insufficient_history:{len(history)}/{_MIN_BARS}"
                continue
            latest = float(history.iloc[-1])
            returns_rows[symbol] = {
                f"r{horizon}": latest / float(history.iloc[-horizon - 1]) - 1.0 for horizon in _HORIZONS
            }

        if not returns_rows:
            return _error(
                "no symbol has the 127 completed sessions required for R126",
                common_date=common_date.date().isoformat(),
                failed_symbols=failed_reasons,
            )

        returns = pd.DataFrame.from_dict(returns_rows, orient="index")
        payload = {
            "status": "ok",
            "as_of_requested": as_of.date().isoformat(),
            "common_date": common_date.date().isoformat(),
            "universe": universe_name,
            "constituent_source": constituent_source,
            "constituent_source_date": constituent_date,
            "survivorship_bias": survivorship_bias,
            "universe_metadata": universe_metadata if universe_name == "us_all_current_filtered" else None,
            "price_adjustment": "split-and-dividend adjusted (yfinance auto_adjust=True)",
            "data_source": "yfinance batch download",
            "universe_count": len(symbols),
            "ranked_count": len(returns_rows),
            "failed_count": len(failed_reasons),
            "failed_symbols": failed_reasons,
            "duplicate_symbols": sorted(set(duplicate_symbols)),
            "horizons": list(_HORIZONS),
            "selection": (
                f"union of each horizon's top {candidate_pct}%; core if top 1% and watch if top 2% in any horizon"
            ),
            "candidate_pct": candidate_pct,
            "candidates": _rank_rows(returns, candidate_pct=candidate_pct),
        }
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)
