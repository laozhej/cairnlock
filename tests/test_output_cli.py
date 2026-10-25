"""Tests for CLI and output formats."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairnlock.cli import app
from cairnlock.models import Finding
from cairnlock.output import render_json, render_sarif, render_text
from cairnlock.rules import RULE_META

runner = CliRunner()


@pytest.mark.parametrize("rule_id", sorted(RULE_META))
def test_cli_explain_registered_rule(rule_id: str) -> None:
    result = runner.invoke(app, ["--no-banner", "explain", rule_id])
    assert result.exit_code == 0
    assert result.stdout.startswith(f"{rule_id}\n")
    assert RULE_META[rule_id] in result.stdout
    assert "Profile: " in result.stdout
    assert "Scope: " in result.stdout
    assert "Severity: " in result.stdout
    assert f"https://github.com/pennacle-security/cairnlock/blob/main/docs/rules.md#{rule_id.lower()}" in result.stdout


@pytest.mark.parametrize(
    ("rule_id", "profile", "scope", "severity"),
    [
        ("PIN001", "core", "JSON descriptions, SKILL.md frontmatter", "high"),
        ("MCP002", "core", "MCP JSON configs", "medium"),
        ("HUC001", "core", "all context files", "high/medium/low"),
        ("SEC001", "extended", "all scanned files", "high/medium"),
    ],
)
def test_cli_explain_rule_details(rule_id: str, profile: str, scope: str, severity: str) -> None:
    result = runner.invoke(app, ["--no-banner", "explain", rule_id])
    assert result.exit_code == 0
    assert f"Profile: {profile}\n" in result.stdout
    assert f"Scope: {scope}\n" in result.stdout
    assert f"Severity: {severity}\n" in result.stdout


def test_cli_explain_unknown_rule() -> None:
    result = runner.invoke(app, ["--no-banner", "explain", "UNKNOWN"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Unknown rule ID: UNKNOWN" in result.stderr
    assert f"Valid rule IDs: {', '.join(sorted(RULE_META))}" in result.stderr


def test_cli_explain_requires_rule_id() -> None:
    result = runner.invoke(app, ["--no-banner", "explain"])
    assert result.exit_code == 2


def test_render_text() -> None:
    findings = [
        Finding(
            rule_id="HUC001",
            severity="medium",
            path="AGENTS.md",
            line=2,
            message="zero-width space (U+200B)",
        ),
    ]
    out = render_text(findings)
    assert "AGENTS.md:2" in out
    assert "[HUC001]" in out
    assert "(medium)" in out


def test_render_text_empty() -> None:
    assert render_text([]) == "no findings"


def test_render_json() -> None:
    findings = [
        Finding(rule_id="HUC001", severity="medium", path="AGENTS.md", line=2, message="test"),
    ]
    out = render_json(findings)
    data = json.loads(out)
    assert data["total"] == 1
    assert data["findings"][0]["rule_id"] == "HUC001"


def test_render_sarif_structure() -> None:
    findings = [
        Finding(rule_id="HUC001", severity="high", path="AGENTS.md", line=2, message="test"),
    ]
    out = render_sarif(findings)
    data = json.loads(out)
    assert data["version"] == "2.1.0"
    assert data["runs"][0]["tool"]["driver"]["name"] == "cairnlock"
    assert len(data["runs"][0]["results"]) == 1
    assert data["runs"][0]["results"][0]["ruleId"] == "HUC001"
    assert data["runs"][0]["results"][0]["level"] == "error"


def test_cli_scan_text() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "AGENTS.md").write_text("# Agents\n\nHello\u200b world.\n", encoding="utf-8")
        result = runner.invoke(app, ["scan", str(root)])
        assert result.exit_code == 1
        assert "HUC001" in result.output


def test_cli_scan_no_fail() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "AGENTS.md").write_text("# Agents\n\nHello\u200b world.\n", encoding="utf-8")
        result = runner.invoke(app, ["scan", str(root), "--no-fail"])
        assert result.exit_code == 0


def test_cli_scan_json_output() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "AGENTS.md").write_text("# Agents\n\nHello.\n", encoding="utf-8")
        out_file = root / "report.json"
        result = runner.invoke(
            app, ["scan", str(root), "--format", "json", "--output", str(out_file)]
        )
        assert result.exit_code == 0
        data = json.loads(out_file.read_text())
        assert data["total"] == 0


def test_cli_scan_sarif_output() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "AGENTS.md").write_text("# Agents\n\nHello.\n", encoding="utf-8")
        out_file = root / "report.sarif"
        result = runner.invoke(
            app, ["scan", str(root), "--format", "sarif", "--output", str(out_file)]
        )
        assert result.exit_code == 0
        data = json.loads(out_file.read_text())
        assert data["version"] == "2.1.0"


def test_cli_init_verify_approve_cycle() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "AGENTS.md").write_text("# Agents\n\nHello.\n", encoding="utf-8")
        # init
        result = runner.invoke(app, ["--no-banner", "init", str(root)])
        assert result.exit_code == 0
        assert "Wrote" in result.output or "wrote" in result.output
        # verify (unchanged)
        result = runner.invoke(app, ["--no-banner", "verify", str(root)])
        assert result.exit_code == 0
        assert "ok" in result.output.lower() or "OK" in result.output
        # modify
        (root / "AGENTS.md").write_text("# Agents\n\nChanged.\n", encoding="utf-8")
        result = runner.invoke(app, ["--no-banner", "verify", str(root)])
        assert result.exit_code == 1
        assert "verify failed" in result.output.lower()
        # diff
        result = runner.invoke(app, ["--no-banner", "diff", str(root)])
        assert result.exit_code == 0
        assert "modified: AGENTS.md" in result.output
        # approve
        result = runner.invoke(app, ["--no-banner", "approve", "AGENTS.md", "--root", str(root)])
        assert result.exit_code == 0
        assert "approved" in result.output.lower()
        # verify again
        result = runner.invoke(app, ["--no-banner", "verify", str(root)])
        assert result.exit_code == 0


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "cairnlock" in result.output
