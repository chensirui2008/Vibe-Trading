"""MCP wrapper contract for screen_momentum."""

from __future__ import annotations

import inspect
import asyncio

import mcp_server
from src.tools.momentum_screener_tool import MomentumScreenerTool


_SCREEN = getattr(mcp_server.screen_momentum, "fn", None) or getattr(
    mcp_server.screen_momentum, "__wrapped__", mcp_server.screen_momentum
)


class _RecordingRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name: str, args: dict) -> str:
        self.calls.append((name, args))
        return '{"status":"ok"}'


def test_wrapper_signature_matches_tool_schema() -> None:
    signature = inspect.signature(_SCREEN)
    assert set(signature.parameters) == set(MomentumScreenerTool.parameters["properties"])
    required = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    assert required == set(MomentumScreenerTool.parameters["required"])


def test_wrapper_forwards_default_and_custom_universes(monkeypatch) -> None:
    registry = _RecordingRegistry()
    monkeypatch.setattr(mcp_server, "_get_registry", lambda: registry)

    _SCREEN(as_of="2026-08-10")
    _SCREEN(as_of="2026-08-10", symbols=["AAPL", "MSFT.US"])

    assert registry.calls == [
        (
            "screen_momentum",
            {
                "as_of": "2026-08-10",
                "universe": "us_all",
                "candidate_pct": 2,
            },
        ),
        (
            "screen_momentum",
            {
                "as_of": "2026-08-10",
                "universe": "us_all",
                "symbols": ["AAPL", "MSFT.US"],
                "candidate_pct": 2,
            },
        ),
    ]


def test_mcp_annotations_are_readonly_idempotent_and_open_world() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}
    annotations = tools["screen_momentum"].annotations
    assert annotations.readOnlyHint is True
    assert annotations.idempotentHint is True
    assert annotations.destructiveHint is False
    assert annotations.openWorldHint is True
