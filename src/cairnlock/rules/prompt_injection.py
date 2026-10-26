"""Prompt-injection phrases in tool and skill descriptions.

Rule ID: PIN001
Scans description fields in JSON configs (opencode.json, .mcp.json) and
frontmatter description in SKILL.md files.
"""

from __future__ import annotations

import json
import re

from cairnlock.models import Finding

RULE_ID = "PIN001"

RULE_IDS = ("PIN001",)

_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts)",
        r"disregard (?:all |any )?(?:previous|prior|above)",
        r"forget (?:all |your )?(?:previous|prior) (?:instructions|prompts)",
        r"reveal (?:your |the )?(?:system )?(?:prompt|instructions)",
        r"print (?:your |the )?(?:system )?(?:prompt|instructions)",
        r"you are now (?:a|an|the) ",
        r"act as (?:a|an) .{0,40}with no (?:restrictions|filters|limits)",
        r"disable (?:all |your )?(?:safety|guardrails?|content filter)",
        r"do anything now",
        r"developer mode",
        r"jailbreak",
        r"send (?:all )?(?:the )?(?:data|context|conversation|history|credentials) to",
        r"exfiltrate",
    )
]

_INDONESIAN_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\babaikan\s+(?:semua\s+)?instruksi\s+sebelumnya\b",
        r"\bungkapkan\s+(?:system\s+prompt|prompt\s+sistem)\b",
        r"\bkirim\s+semua\s+data\s+ke\b",
        r"\bsembunyikan\s+dari\s+pengguna\b",
        r"\bbertindak\s+tanpa\s+batasan\b",
    )
]

_FRONTMATTER_DESC = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def applies_to(rel_path: str) -> bool:
    return rel_path.endswith(".json") or rel_path.endswith("SKILL.md")


def _json_descriptions(text: str) -> list[tuple[int, str]]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    values: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "description" and isinstance(value, str):
                    values.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    out: list[tuple[int, str]] = []
    pos = 0
    for value in values:
        idx = text.find('"description"', pos)
        line = text.count("\n", 0, idx) + 1 if idx != -1 else 0
        pos = idx + 1 if idx != -1 else pos
        out.append((line, value))
    return out


def _frontmatter_descriptions(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return []
    frontmatter = "\n".join(lines[1:end])
    try:
        import yaml

        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    value = data.get("description")
    if not isinstance(value, str):
        return []
    m = _FRONTMATTER_DESC.search(frontmatter)
    if m:
        # frontmatter starts at file line 2 (after the first ---)
        line = 2 + frontmatter[: m.start()].count("\n")
    else:
        line = 2
    return [(line, value)]


def check(rel_path: str, text: str) -> list[Finding]:
    if rel_path.endswith(".json"):
        descriptions = _json_descriptions(text)
    else:
        descriptions = _frontmatter_descriptions(text)

    findings: list[Finding] = []
    for line, value in descriptions:
        for pat in (*_PATTERNS, *_INDONESIAN_PATTERNS):
            m = pat.search(value)
            if m:
                snippet = m.group(0)[:60]
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        severity="high",
                        path=rel_path,
                        line=line,
                        message=f'prompt-injection phrase in description: "{snippet}"',
                    )
                )
                break  # one finding per description
    return findings
