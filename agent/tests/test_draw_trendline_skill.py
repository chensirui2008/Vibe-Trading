"""Contract tests for the bundled draw-trendline backend skill."""

from __future__ import annotations

from pathlib import Path

from src.agent.skills import SkillsLoader


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "agent" / "src" / "skills" / "draw-trendline"


def test_draw_trendline_is_in_backend_skill_directory() -> None:
    assert (SKILL_ROOT / "SKILL.md").is_file()


def test_skills_loader_registers_draw_trendline() -> None:
    loader = SkillsLoader(
        user_skills_dir=REPO_ROOT / "agent" / "tests" / "fixtures" / "missing"
    )
    assert "draw-trendline" in {skill.name for skill in loader.skills}


def test_draw_trendline_weekly_first_contract() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    required = (
        "name: draw-trendline",
        "category: analysis",
        "先生成周线图并完成周线趋势线判断，再生成日线图",
        'interval="1D"',
        'resample("W-FRI"',
        "weekly projection",
        "两个触点只能得到 `candidate`",
        "才标为 `validated`",
        "anchor_mode=wick",
        "anchor_mode=body",
        "no_clear_trendline",
        "timeframe_divergence",
        "不调用交易、账户写入、下单或撤单工具",
    )
    for marker in required:
        assert marker in text


def test_draw_trendline_does_not_use_unsupported_weekly_interval() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert 'interval="1W"' not in text
    assert 'interval="1wk"' not in text
