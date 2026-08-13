"""Deterministic diagnostics for a fixed breakout-base window."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from src.agent.tools import BaseTool


def _error(message: str, **details: Any) -> str:
    return json.dumps(
        {"status": "error", "error": message, **details},
        ensure_ascii=False,
        allow_nan=False,
    )


def _default_history_fetcher(symbol: str, start: str, end: str) -> tuple[pd.DataFrame, str]:
    from src.market_data import fetch_market_data

    payload = fetch_market_data(
        codes=[symbol],
        start_date=start,
        end_date=end,
        source="auto",
        interval="1D",
        max_rows=0,
        include_provenance=True,
    )
    records = payload.get(symbol)
    if not isinstance(records, list) or not records:
        unresolved = payload.get("_unresolved") or []
        raise ValueError(f"no OHLCV returned; unresolved={unresolved}")
    frame = pd.DataFrame(records)
    date_column = "trade_date" if "trade_date" in frame.columns else "date"
    if date_column not in frame.columns:
        raise ValueError("OHLCV response has no trade_date/date column")
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop(date_column))).tz_localize(None)
    provenance = (payload.get("_provenance") or {}).get(symbol) or {}
    return frame, str(provenance.get("source") or "auto")


def _confirmed_pivots(values: pd.Series, *, left: int, right: int, high: bool) -> list[int]:
    result: list[int] = []
    for index in range(left, len(values) - right):
        center = float(values.iloc[index])
        neighbors = pd.concat([values.iloc[index - left : index], values.iloc[index + 1 : index + right + 1]])
        if (center > neighbors).all() if high else (center < neighbors).all():
            result.append(index)
    return result


def _ratio(numerator: float, denominator: float) -> float | None:
    if not math.isfinite(denominator) or denominator <= 0:
        return None
    return numerator / denominator


class BreakoutSetupTool(BaseTool):
    """Measure a user-fixed base without letting the model hand-wave metrics."""

    name = "analyze_breakout_setup"
    description = (
        "Read-only deterministic diagnostics for one U.S. stock breakout setup. "
        "Given an explicit platform_start and as_of date, fetches full daily OHLCV "
        "and measures base drawdown/width, normalized true-range contraction, volume "
        "contraction, shock recovery, moving-average slopes, and confirmed 3-3 pivots. "
        "It reports evidence and major contraindications; strategy thresholds remain "
        "ideal references rather than automatic single-factor exclusions."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "One U.S. symbol such as AXON or AXON.US.",
            },
            "platform_start": {
                "type": "string",
                "description": "Fixed first session of the proposed base, YYYY-MM-DD.",
            },
            "as_of": {
                "type": "string",
                "description": "Inclusive analysis cutoff, YYYY-MM-DD.",
            },
            "pivot_left": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            "pivot_right": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
        },
        "required": ["symbol", "platform_start", "as_of"],
        "additionalProperties": False,
    }
    repeatable = True
    is_readonly = True

    def __init__(
        self,
        *,
        history_fetcher: Callable[[str, str, str], tuple[pd.DataFrame, str]] | None = None,
    ) -> None:
        self._history_fetcher = history_fetcher or _default_history_fetcher

    def execute(self, **kwargs: Any) -> str:
        raw_symbol = kwargs.get("symbol")
        if not isinstance(raw_symbol, str) or not raw_symbol.strip():
            return _error("symbol must be a non-empty string")
        symbol = raw_symbol.strip().upper()
        if not symbol.endswith(".US"):
            symbol = f"{symbol}.US"

        try:
            platform_start = pd.Timestamp(kwargs.get("platform_start")).normalize()
            as_of = pd.Timestamp(kwargs.get("as_of")).normalize()
        except Exception:
            return _error("platform_start and as_of must use YYYY-MM-DD format")
        if platform_start > as_of:
            return _error("platform_start cannot be after as_of")
        if as_of.date() > date.today():
            return _error("as_of cannot be in the future")

        pivot_left = kwargs.get("pivot_left", 3)
        pivot_right = kwargs.get("pivot_right", 3)
        for name, value in (("pivot_left", pivot_left), ("pivot_right", pivot_right)):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
                return _error(f"{name} must be an integer from 1 to 10")

        fetch_start = platform_start - pd.Timedelta(days=60)
        try:
            frame, source = self._history_fetcher(
                symbol,
                fetch_start.strftime("%Y-%m-%d"),
                as_of.strftime("%Y-%m-%d"),
            )
        except Exception as exc:
            return _error(f"OHLCV fetch failed: {exc}", symbol=symbol)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return _error("OHLCV fetch returned an empty frame", symbol=symbol)

        required = {"open", "high", "low", "close", "volume"}
        missing = sorted(required - set(frame.columns))
        if missing:
            return _error("OHLCV frame is missing required columns", missing_columns=missing)
        cleaned = frame.copy()
        cleaned.index = pd.DatetimeIndex(pd.to_datetime(cleaned.index)).tz_localize(None).normalize()
        cleaned = cleaned[~cleaned.index.duplicated(keep="last")].sort_index()
        for column in required:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
        cleaned = cleaned.dropna(subset=list(required))
        cleaned = cleaned[(cleaned.index <= as_of) & (cleaned["close"] > 0)]
        base = cleaned.loc[cleaned.index >= platform_start].copy()
        minimum_bars = pivot_left + pivot_right + 2
        if len(base) < minimum_bars:
            return _error(
                "proposed base has too few complete sessions",
                symbol=symbol,
                base_bars=len(base),
                required_bars=minimum_bars,
            )

        previous_close = cleaned["close"].shift(1)
        true_range = pd.concat(
            [
                cleaned["high"] - cleaned["low"],
                (cleaned["high"] - previous_close).abs(),
                (cleaned["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        cleaned["normalized_tr"] = true_range / previous_close
        base["normalized_tr"] = cleaned.loc[base.index, "normalized_tr"]

        running_high = base["high"].cummax()
        max_drawdown = float((base["low"] / running_high - 1.0).min())
        width = float(base["high"].max() / base["low"].min() - 1.0)
        split = max(1, len(base) // 2)
        first = base.iloc[:split]
        second = base.iloc[split:]
        recent = base.iloc[-min(5, len(base)) :]
        tr_first = float(first["normalized_tr"].median())
        tr_second = float(second["normalized_tr"].median())
        tr_recent = float(recent["normalized_tr"].median())
        tr_platform = float(base["normalized_tr"].median())
        volume_first = float(first["volume"].median())
        volume_second = float(second["volume"].median())

        shock_dates: list[str] = []
        for timestamp in base.index:
            prior = cleaned.loc[cleaned.index < timestamp, "normalized_tr"].dropna().tail(20)
            if len(prior) == 20 and float(base.at[timestamp, "normalized_tr"]) >= 2 * float(prior.median()):
                shock_dates.append(timestamp.date().isoformat())
        last_shock = pd.Timestamp(shock_dates[-1]) if shock_dates else None
        sessions_since_shock = int((base.index > last_shock).sum()) if last_shock is not None else None
        shock_recovered: bool | None = None
        if last_shock is not None:
            prior = cleaned.loc[cleaned.index < last_shock, "normalized_tr"].dropna().tail(20)
            after = base.loc[base.index > last_shock, "normalized_tr"].dropna()
            shock_recovered = bool(
                len(prior) == 20 and len(after) >= 10 and float(after.tail(5).median()) < float(prior.median())
            )

        high_positions = _confirmed_pivots(base["high"], left=pivot_left, right=pivot_right, high=True)
        low_positions = _confirmed_pivots(base["low"], left=pivot_left, right=pivot_right, high=False)
        pivot: dict[str, Any] | None = None
        if high_positions:
            position = high_positions[-1]
            pivot_date = base.index[position]
            pivot_price = float(base["high"].iloc[position])
            after_pivot = base.iloc[position + 1 :]
            pivot_drawdown = float(after_pivot["low"].min() / pivot_price - 1.0) if not after_pivot.empty else 0.0
            pivot = {
                "date": pivot_date.date().isoformat(),
                "price": pivot_price,
                "sessions_ago": int(len(base) - 1 - position),
                "distance": float(base["close"].iloc[-1] / pivot_price - 1.0),
                "post_pivot_max_drawdown": pivot_drawdown,
                "in_second_half": bool(position >= split),
            }

        sma10 = cleaned["close"].rolling(10).mean()
        sma20 = cleaned["close"].rolling(20).mean()
        sma10_rising = bool(len(sma10.dropna()) >= 6 and sma10.iloc[-1] > sma10.iloc[-6])
        sma20_rising = bool(len(sma20.dropna()) >= 6 and sma20.iloc[-1] > sma20.iloc[-6])

        tr_recent_to_second = _ratio(tr_recent, tr_second)
        recent_max_to_platform = _ratio(float(recent["normalized_tr"].max()), tr_platform)
        contraindications: list[dict[str, str]] = []
        if max_drawdown < -0.25:
            contraindications.append({"severity": "major", "code": "deep_base_drawdown"})
        elif max_drawdown < -0.15:
            contraindications.append({"severity": "moderate", "code": "drawdown_above_ideal"})
        if width > 0.30:
            contraindications.append({"severity": "major", "code": "very_wide_base"})
        elif width > 0.20:
            contraindications.append({"severity": "moderate", "code": "width_above_ideal"})
        if tr_recent_to_second is not None and tr_recent_to_second > 1.20:
            contraindications.append({"severity": "major", "code": "recent_volatility_expansion"})
        elif tr_recent_to_second is not None and tr_recent_to_second > 0.90:
            contraindications.append({"severity": "moderate", "code": "weak_recent_contraction"})
        if recent_max_to_platform is not None and recent_max_to_platform > 2.0:
            contraindications.append({"severity": "major", "code": "recent_range_spike"})
        if shock_recovered is False:
            contraindications.append({"severity": "major", "code": "unrecovered_price_shock"})
        if pivot is None:
            contraindications.append({"severity": "moderate", "code": "no_confirmed_pivot"})

        major_count = sum(item["severity"] == "major" for item in contraindications)
        structure_assessment = "contradicted" if major_count >= 1 else ("mixed" if contraindications else "coherent")
        low_points = [
            {"date": base.index[pos].date().isoformat(), "price": float(base["low"].iloc[pos])} for pos in low_positions
        ]
        payload = {
            "status": "ok",
            "symbol": symbol,
            "source": source,
            "actual_end": base.index[-1].date().isoformat(),
            "platform_start": base.index[0].date().isoformat(),
            "base_bars": len(base),
            "ideal_references": {
                "base_bars": "10-42",
                "max_drawdown": "<=15%",
                "width": "<=20%",
                "second_half_tr_ratio": "<=85%",
                "recent_to_second_tr_ratio": "<=90%",
                "second_half_volume_ratio": "<=90%",
            },
            "metrics": {
                "max_drawdown": max_drawdown,
                "width": width,
                "second_to_first_tr_ratio": _ratio(tr_second, tr_first),
                "recent_to_second_tr_ratio": tr_recent_to_second,
                "recent_max_to_platform_tr_ratio": recent_max_to_platform,
                "second_to_first_volume_ratio": _ratio(volume_second, volume_first),
                "sma10_rising": sma10_rising,
                "sma20_rising": sma20_rising,
            },
            "shock": {
                "dates": shock_dates,
                "sessions_since_last": sessions_since_shock,
                "recovered": shock_recovered,
            },
            "confirmed_pivot": pivot,
            "confirmed_lows": low_points,
            "higher_lows": bool(len(low_points) >= 2 and low_points[-1]["price"] > low_points[-2]["price"]),
            "contraindications": contraindications,
            "structure_assessment": structure_assessment,
            "interpretation": (
                "Metrics are deterministic diagnostics. Numeric thresholds are ideal "
                "references; the skill assigns the final graded setup label."
            ),
        }
        return json.dumps(payload, ensure_ascii=False, allow_nan=False)
