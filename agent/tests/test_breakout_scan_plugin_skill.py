"""Contract tests for the Codex-native breakout-scan plugin skill."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "vibe-trading"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "breakout-scan"


def test_plugin_exposes_breakout_scan_skill() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["skills"] == "./skills/"
    assert (SKILL_ROOT / "SKILL.md").is_file()


def test_breakout_scan_trigger_and_method_contract() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "name: breakout-scan",
        "突破策略选股",
        "R21",
        "R63",
        "R126",
        "前 1%",
        "前 2%",
        "10–42",
        "3-3 pivot",
        "screen_market",
        "screen_momentum",
        'universe="sp500"',
        "当前 S&P 500 成分代理排名",
        "failed_symbols",
    )
    for marker in required:
        assert marker in text


def test_breakout_scan_allows_implicit_invocation() -> None:
    metadata = yaml.safe_load(
        (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )
    assert metadata["policy"]["allow_implicit_invocation"] is True
    assert "$breakout-scan" in metadata["interface"]["default_prompt"]
