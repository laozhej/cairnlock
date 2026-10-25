"""Typer CLI entry points with rich UX."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from cairnlock import __version__, lockfile, vcs
from cairnlock import baseline as baseline_mod
from cairnlock.ascii_art import get_banner
from cairnlock.config import ConfigError, is_ignored, load_config
from cairnlock.output import render_html, render_json, render_markdown, render_sarif, render_text
from cairnlock.rules import PROFILE_NAMES, PROFILE_RULES
from cairnlock.scanner import check_file, discover_files

app = typer.Typer(
    add_completion=False,
    help="Static analyzer and lockfile for AI-agent context files.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

console = Console()
err_console = Console(stderr=True)

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}

_RULE_DETAILS = {
    "HUC001": ("all context files", "high/medium/low"),
    "PIN001": ("JSON descriptions, SKILL.md frontmatter", "high"),
    "REM001": ("SKILL.md, skills/ files", "high/medium"),
    "MCP001": ("MCP JSON configs", "high"),
    "MCP002": ("MCP JSON configs", "medium"),
    "MCP003": ("MCP JSON configs", "medium"),
    "MCP004": ("MCP JSON configs", "high"),
    "UNP001": ("MCP JSON configs", "medium"),
    "SEC001": ("all scanned files", "high/medium"),
    "SHC001": ("source files (extended)", "high/medium"),
    "NET001": ("source files (extended)", "high/medium"),
    "FSY001": ("source files (extended)", "high/medium"),
    "ENV001": ("source files (extended)", "high/medium"),
    "PRI001": ("source files (extended)", "high/medium"),
    "OBF001": ("source files, non-skill (extended)", "high/medium/low"),
    "SUP001": ("dependency files (extended)", "high/medium/low"),
    "CFG001": ("config files, non-markdown (extended)", "high/medium"),
    "TOO001": ("tool definitions, JSON configs", "high/medium"),
    "CRY001": ("source files (extended)", "high/medium/low"),
}


class OutputFormat(StrEnum):
    text = "text"
    json = "json"
    sarif = "sarif"
    html = "html"
    markdown = "md"


class SeverityFilter(StrEnum):
    all = "all"
    high = "high"
    medium = "medium"
    low = "low"


class FailOn(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    never = "never"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(get_banner(__version__, compact=True), err=True)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
    no_banner: bool = typer.Option(False, "--no-banner", help="Hide ASCII banner."),
) -> None:
    """Static analyzer and lockfile for AI-agent context files."""
    if not no_banner and not quiet and not version:
        typer.echo(get_banner(__version__), err=True)


def _render(findings: list, fmt: OutputFormat) -> str:
    if fmt is OutputFormat.json:
        return render_json(findings)
    if fmt is OutputFormat.sarif:
        return render_sarif(findings)
    if fmt is OutputFormat.html:
        return render_html(findings)
    if fmt is OutputFormat.markdown:
        return render_markdown(findings)
    return render_text(findings)


def _filter_findings(findings: list, severity: SeverityFilter) -> list:
    if severity == SeverityFilter.all:
        return findings
    return [f for f in findings if f.severity == severity.value]


def _print_summary(findings: list, verbose: bool = False) -> None:
    if not findings:
        console.print("[green]no findings[/green]")
        return

    by_severity = {"high": 0, "medium": 0, "low": 0}
    by_rule = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1

    table = Table(title="Scan Summary", show_header=True, header_style="bold magenta")
    table.add_column("Severity", style="bold")
    table.add_column("Count", justify="right")
    for sev in ("high", "medium", "low"):
        if by_severity.get(sev, 0):
            color = {"high": "red", "medium": "yellow", "low": "blue"}[sev]
            table.add_row(f"[{color}]{sev.upper()}[/{color}]", str(by_severity[sev]))
    table.add_row("TOTAL", str(len(findings)), style="bold")
    console.print(table)

    if verbose and by_rule:
        rule_table = Table(title="By Rule", show_header=True, header_style="bold cyan")
        rule_table.add_column("Rule ID")
        rule_table.add_column("Count", justify="right")
        for rid, count in sorted(by_rule.items(), key=lambda x: -x[1]):
            rule_table.add_row(rid, str(count))
        console.print(rule_table)


@app.command(name="scan")
def scan_cmd(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Directory to scan.")] = Path("."),
    fmt: Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format.")] = OutputFormat.text,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write report to file.")] = None,
    no_fail: Annotated[bool, typer.Option("--no-fail", help="Exit 0 even when findings exist.")] = False,
    fail_on: Annotated[
        FailOn | None,
        typer.Option(
            "--fail-on",
            help="Exit 1 only when a finding at or above this severity exists. "
            "Overrides cairnlock.toml.",
        ),
    ] = None,
    severity: Annotated[SeverityFilter, typer.Option("--severity", "-s", help="Report only this severity.")] = SeverityFilter.all,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Rule set: core (agent context files, default) or extended "
            "(generic rules plus source and dependency files). Overrides cairnlock.toml.",
        ),
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option("--baseline", help="JSON file of known finding fingerprints; only new findings are reported."),
    ] = None,
    write_baseline: Annotated[
        Path | None,
        typer.Option("--write-baseline", help="Save current finding fingerprints to this file and exit 0."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")] = False,
    show_progress: Annotated[bool, typer.Option("--progress/--no-progress", help="Show progress bar.")] = True,
) -> None:
    """Scan agent context files under PATH for risk patterns."""
    try:
        config = load_config(path)
    except ConfigError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc

    if profile is not None:
        if profile not in PROFILE_NAMES:
            err_console.print(
                f"[red]error:[/red] --profile must be one of: {', '.join(PROFILE_NAMES)}"
            )
            raise typer.Exit(2)
        config.profile = profile
    allowed = PROFILE_RULES.get(config.profile)
    include_code = config.profile == "extended"

    if verbose:
        err_console.print(f"Scanning: {path.absolute()} (profile: {config.profile})")

    files = list(discover_files(path, include_code=include_code))
    if not files:
        console.print("[yellow]No agent context files found[/yellow]")
        return

    disabled = set(config.disabled_rules)
    ignore = config.ignore
    findings: list = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=err_console,
        disable=not show_progress or fmt is not OutputFormat.text or len(files) < 5,
    ) as progress:
        task = progress.add_task("Scanning files...", total=len(files))
        for p in files:
            rel = p.relative_to(path).as_posix()
            progress.advance(task)
            if ignore and is_ignored(rel, ignore):
                continue
            try:
                if p.stat().st_size > 1_000_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            findings.extend(check_file(rel, text, disabled, allowed))

    findings.sort(key=lambda f: (f.path, f.line, f.rule_id))
    findings = _filter_findings(findings, severity)

    baseline_fps: set[str] = set()
    if baseline is not None:
        try:
            baseline_fps = baseline_mod.load_baseline(baseline)
        except ValueError as exc:
            err_console.print(f"[red]error:[/red] {exc}")
            raise typer.Exit(2) from exc
        before = len(findings)
        findings = [f for f in findings if baseline_mod.fingerprint(f) not in baseline_fps]
        suppressed = before - len(findings)
    else:
        suppressed = 0

    if write_baseline is not None:
        baseline_mod.write_baseline(write_baseline, findings)
        err_console.print(
            f"[green]OK:[/green] Wrote {len(findings)} fingerprints to {write_baseline}"
        )
        return

    report = _render(findings, fmt)
    if output is not None:
        output.write_text(report + "\n", encoding="utf-8")
        err_console.print(f"[green]OK:[/green] Wrote {len(findings)} findings to {output}")
    elif fmt is OutputFormat.text:
        console.print(report)
    else:
        typer.echo(report)

    if fmt is OutputFormat.text:
        console.print()
        _print_summary(findings, verbose=verbose)
        if baseline is not None:
            console.print(f"suppressed by baseline: {suppressed}")

    effective_fail_on = fail_on.value if fail_on is not None else config.fail_on
    if no_fail or effective_fail_on == "never":
        return
    threshold = SEVERITY_RANK[effective_fail_on]
    if any(SEVERITY_RANK.get(f.severity, 0) >= threshold for f in findings):
        raise typer.Exit(1)


@app.command()
def init(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Repository root.")] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing lockfile.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")] = False,
) -> None:
    """Record SHA-256 hashes of all tracked agent context files in cairnlock.lock."""
    lock_path = path / lockfile.LOCKFILE_NAME
    if lock_path.exists() and not force:
        console.print(f"[red]error:[/red] {lockfile.LOCKFILE_NAME} already exists; use --force to overwrite")
        raise typer.Exit(1)
    files = lockfile.hashes(path)
    if not files:
        console.print("[yellow]warning:[/yellow] no agent context files found")
    lockfile.write(path, files)
    console.print(f"[green]OK:[/green] Wrote {lockfile.LOCKFILE_NAME} with {len(files)} files")
    if verbose:
        for rel, h in sorted(files.items()):
            console.print(f"  {rel}  [dim]{h[:16]}...[/dim]")


def _lock_changed_vs_base(root: Path, base_lock: dict) -> bool:
    """Compare the working lockfile to the base lockfile semantically."""
    working = lockfile.load(root)
    if working is None:
        return True  # deleted or unreadable in the working tree
    return (working.get("version"), working.get("files")) != (
        base_lock.get("version"),
        base_lock.get("files"),
    )


def _verify_against_base(root: Path, base: str, allow_lock_change: bool) -> None:
    """Compare the working tree against the lockfile stored at a git ref.

    Exit codes: 0 clean, 1 changes found, 2 usage or environment error.
    """
    try:
        base_text = vcs.read_file_at(root, base, lockfile.LOCKFILE_NAME)
    except vcs.GitUsageError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except vcs.GitEnvError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc

    if base_text is None:
        console.print(
            f"[red]error:[/red] no {lockfile.LOCKFILE_NAME} at ref '{base}'; "
            "run 'cairnlock init' on the base branch first"
        )
        raise typer.Exit(2)

    base_lock = lockfile.loads(base_text)
    if base_lock is None:
        console.print(
            f"[red]error:[/red] {lockfile.LOCKFILE_NAME} at ref '{base}' is not a valid lockfile"
        )
        raise typer.Exit(2)

    current_hashes = lockfile.hashes(root)
    base_files = base_lock["files"]
    findings: list[str] = []
    for rel in sorted(p for p in current_hashes if p in base_files and current_hashes[p] != base_files[p]):
        findings.append(f"modified: {rel}")
    for rel in sorted(p for p in current_hashes if p not in base_files):
        findings.append(f"added: {rel}")
    for rel in sorted(p for p in base_files if p not in current_hashes):
        findings.append(f"deleted: {rel}")

    lock_changed = _lock_changed_vs_base(root, base_lock)
    if lock_changed and not allow_lock_change:
        findings.insert(0, "lockfile modified in this change")

    if not findings:
        console.print(f"ok: no changes vs base '{base}'")
        return

    for line in findings:
        console.print(f"  {line}")
    console.print(f"[red]verify failed:[/red] {len(findings)} findings vs base '{base}'")
    if lock_changed and allow_lock_change:
        console.print("note: lockfile change allowed by --allow-lock-change")
    raise typer.Exit(1)


@app.command()
def verify(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Repository root.")] = Path("."),
    base: Annotated[
        str | None,
        typer.Option("--base", help="Git ref to read the base cairnlock.lock from."),
    ] = None,
    allow_lock_change: Annotated[
        bool,
        typer.Option(
            "--allow-lock-change",
            help="Do not fail when cairnlock.lock itself differs from --base.",
        ),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")] = False,
) -> None:
    """Fail if tracked files changed without approval, or differ from --base.

    Exit codes: 0 clean, 1 changes found, 2 usage or environment error.
    """
    if base is not None:
        _verify_against_base(path, base, allow_lock_change)
        return
    lock = lockfile.load(path)
    if lock is None:
        console.print(f"[red]error:[/red] no {lockfile.LOCKFILE_NAME}; run 'cairnlock init' first")
        raise typer.Exit(2)
    changes = lockfile.changes(path, lock)
    tracked = len(lock.get("files", {}))
    if not any(changes.values()):
        console.print(f"ok: {tracked} files unchanged")
        return
    for kind in ("modified", "added", "deleted"):
        for rel in changes[kind]:
            console.print(f"  {kind}: {rel}")
    total = sum(len(v) for v in changes.values())
    console.print(f"[red]verify failed:[/red] {total} changed files")
    console.print("review with 'cairnlock diff', then approve with 'cairnlock approve <file>'")
    raise typer.Exit(1)


@app.command()
def diff(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Repository root.")] = Path("."),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")] = False,
) -> None:
    """Show changes against the lockfile, with findings inside changed files."""
    lock = lockfile.load(path)
    if lock is None:
        console.print(f"[red]error:[/red] no {lockfile.LOCKFILE_NAME}; run 'cairnlock init' first")
        raise typer.Exit(1)
    changes = lockfile.changes(path, lock)
    if not any(changes.values()):
        console.print("ok: no changes")
        return
    changed = [rel for kind in ("modified", "added") for rel in changes[kind]]
    findings = lockfile.diff_findings(path, changed)
    for kind in ("modified", "added", "deleted"):
        for rel in changes[kind]:
            count = sum(1 for f in findings if f.path == rel)
            suffix = f" ({count} finding{'s' if count != 1 else ''})" if kind != "deleted" else ""
            console.print(f"  {kind}: {rel}{suffix}")
    if findings:
        console.print()
        _print_summary(findings, verbose=verbose)


@app.command()
def approve(
    paths: Annotated[list[Path], typer.Argument(..., help="File(s) to approve (relative to --root).")],
    root: Annotated[Path, typer.Option("--root", exists=True, file_okay=False, help="Repository root.")] = Path("."),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")] = False,
) -> None:
    """Mark changed files as reviewed (update hash) or approve deletion (remove entry)."""
    try:
        approved, unknown = lockfile.approve(root, paths)
    except FileNotFoundError as e:
        console.print(f"[red]error:[/red] {e}")
        raise typer.Exit(1) from e
    for rel in approved:
        console.print(f"[green]OK:[/green] Approved: {rel}")
    for unk in unknown:
        console.print(f"[yellow]warning:[/yellow] not tracked or missing: {unk}")
    if unknown:
        raise typer.Exit(1)


@app.command()
def rules(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show detailed rule info.")] = False,
) -> None:
    """List all detection rules with profile and scope."""
    from cairnlock.rules import RULE_META, RULES, rule_ids

    profile_of: dict[str, str] = {}
    for name, ids in PROFILE_RULES.items():
        for rid in ids:
            profile_of[rid] = name

    table = Table(title="Detection Rules", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="bold")
    table.add_column("Profile")
    table.add_column("Scope")
    table.add_column("Description")
    if verbose:
        table.add_column("Module")

    for rule in RULES:
        for rid in sorted(rule_ids(rule)):
            profile = profile_of.get(rid, "?")
            scope, _ = _RULE_DETAILS.get(rid, ("varies", "varies"))
            if verbose:
                table.add_row(rid, profile, scope, RULE_META.get(rid, rid), rule.__name__)
            else:
                table.add_row(rid, profile, scope, RULE_META.get(rid, rid))

    console.print(table)


@app.command()
def explain(
    rule_id: Annotated[str, typer.Argument(help="Rule ID to explain, such as PIN001.")],
) -> None:
    """Explain a detection rule's profile, scope, severity and description."""
    from cairnlock.rules import RULE_META

    if rule_id not in RULE_META:
        typer.echo(f"Unknown rule ID: {rule_id}", err=True)
        typer.echo(f"Valid rule IDs: {', '.join(sorted(RULE_META))}", err=True)
        raise typer.Exit(2)

    profile = next(name for name, ids in PROFILE_RULES.items() if rule_id in ids)
    scope, severity = _RULE_DETAILS[rule_id]
    typer.echo(f"{rule_id}\nProfile: {profile}\nScope: {scope}\nSeverity: {severity}")
    typer.echo(f"Description: {RULE_META[rule_id]}")
    typer.echo(
        f"Reference: https://github.com/pennacle-security/cairnlock/blob/main/docs/rules.md#{rule_id.lower()}"
    )


@app.command()
def stats(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Repository root.")] = Path("."),
) -> None:
    """Show repository statistics for tracked files."""
    files = list(discover_files(path))
    if not files:
        console.print("[yellow]No agent context files found[/yellow]")
        return

    total_size = sum(p.stat().st_size for p in files)
    by_ext = {}
    for p in files:
        ext = p.suffix or "no-ext"
        by_ext[ext] = by_ext.get(ext, 0) + 1

    table = Table(title="Repository Stats", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total files", str(len(files)))
    table.add_row("Total size", f"{total_size:,} bytes ({total_size/1024:.1f} KB)")
    for ext, count in sorted(by_ext.items(), key=lambda x: -x[1]):
        table.add_row(f"  {ext}", str(count))
    console.print(table)
