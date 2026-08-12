"""Contract tests for the Codex-native episodic-pivot-scan plugin skill."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "vibe-trading"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "episodic-pivot-scan"


def test_plugin_exposes_episodic_pivot_scan_skill() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["skills"] == "./skills/"
    assert (SKILL_ROOT / "SKILL.md").is_file()


def test_episodic_pivot_trigger_and_method_contract() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "name: episodic-pivot-scan",
        "事件驱动交易选股",
        "open_gap < 10%",
        "ADV20",
        "volume_progress_15",
        "volume_progress_30",
        "R63_pre_event",
        "R126_pre_event",
        "consensus_unavailable",
        "gap_unverified",
        "failed_reaction",
        "get_stock_news",
        "screen_market",
    )
    for marker in required:
        assert marker in text


def test_episodic_pivot_implicit_invocation_and_scope() -> None:
    metadata = yaml.safe_load(
        (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )
    assert metadata["policy"]["allow_implicit_invocation"] is True
    assert "$episodic-pivot-scan" in metadata["interface"]["default_prompt"]

    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "Do not use for general event research" in text
    assert "不调用交易、账户写入或下单工具" in text
