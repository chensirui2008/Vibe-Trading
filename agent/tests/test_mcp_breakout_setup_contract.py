"""MCP wrapper contract for analyze_breakout_setup."""

from __future__ import annotations

import asyncio
import inspect

import mcp_server
from src.tools.breakout_setup_tool import BreakoutSetupTool


_ANALYZE = getattr(mcp_server.analyze_breakout_setup, "fn", None) or getattr(
    mcp_server.analyze_breakout_setup,
    "__wrapped__",
    mcp_server.analyze_breakout_setup,
)


class _RecordingRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name: str, args: dict) -> str:
        self.calls.append((name, args))
        return '{"status":"ok"}'


def test_wrapper_signature_matches_tool_schema() -> None:
    signature = inspect.signature(_ANALYZE)
    assert set(signature.parameters) == set(BreakoutSetupTool.parameters["properties"])
    required = {
        name for name, parameter in signature.parameters.items() if parameter.default is inspect.Parameter.empty
    }
    assert required == set(BreakoutSetupTool.parameters["required"])


def test_wrapper_forwards_fixed_window(monkeypatch) -> None:
    registry = _RecordingRegistry()
    monkeypatch.setattr(mcp_server, "_get_registry", lambda: registry)
    _ANALYZE(symbol="AXON", platform_start="2026-06-29", as_of="2026-08-11")
    assert registry.calls == [
        (
            "analyze_breakout_setup",
            {
                "symbol": "AXON",
                "platform_start": "2026-06-29",
                "as_of": "2026-08-11",
            },
        )
    ]


def test_annotations_are_readonly_idempotent_and_open_world() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}
    annotations = tools["analyze_breakout_setup"].annotations
    assert annotations.readOnlyHint is True
    assert annotations.idempotentHint is True
    assert annotations.destructiveHint is False
    assert annotations.openWorldHint is True
