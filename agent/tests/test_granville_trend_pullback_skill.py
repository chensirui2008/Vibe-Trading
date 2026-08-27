"""Contract tests for the bundled granville-trend-pullback backend skill."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.agent.skills import SkillsLoader


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "agent" / "src" / "skills" / "granville-trend-pullback"


def test_bundled_distribution_exposes_granville_trend_pullback_skill() -> None:
    assert (SKILL_ROOT / "SKILL.md").is_file()


def test_skills_loader_registers_granville_trend_pullback() -> None:
    loader = SkillsLoader(user_skills_dir=REPO_ROOT / "agent" / "tests" / "fixtures" / "missing")
    skills = {skill.name: skill for skill in loader.skills}

    assert "granville-trend-pullback" in skills
    assert skills["granville-trend-pullback"].category == "strategy"


def test_granville_trend_pullback_method_contract() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "name: granville-trend-pullback",
        "法则 2：假跌破后收复",
        "法则 3：回调获支撑",
        'interval="1d"',
        "lookback=250",
        "max_rows=0",
        "MA[t] > MA[t-20]",
        "Close < MA",
        "Close > MA",
        "Close >= MA",
        "完整交易日收盘",
        "部分符合/等待确认",
        "形态失效",
        "交易止损",
        "未知不得当作部分符合",
        "不调用交易、账户写入或下单工具",
    )
    for marker in required:
        assert marker in text


def test_granville_trend_pullback_implicit_invocation_and_scope() -> None:
    metadata = yaml.safe_load((SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))

    assert metadata["policy"]["allow_implicit_invocation"] is True
    assert "$granville-trend-pullback" in metadata["interface"]["default_prompt"]

    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "不得把盘中一度跌破但收盘始终在均线上方归为法则 2" in text
    assert "法则 2 与法则 3 不得同时判为“符合”" in text
