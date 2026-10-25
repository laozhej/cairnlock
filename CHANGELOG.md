# Changelog

All notable changes to cairnlock are documented in this file.

The format is based on Keep a Changelog 1.1.0, and the project follows
Semantic Versioning 2.0.0.

## [Unreleased]

### Added

- `cairnlock explain <RULE_ID>` prints a rule's profile, scope, severity,
  description and reference link. Unknown IDs exit with status 2 and list
  the valid rule IDs.

## [0.5.0] - 2026-10-25

### Added

- Rule profiles, per the approved rules audit:
  - `core` (default): agent-specific rules on agent context files.
  - `extended`: generic rules plus widened discovery for source files
    (`.py`, `.js`, `.ts`) and dependency files (`requirements*`,
    `package.json`, `pyproject.toml`, `setup.py`, `setup.cfg`).
  - `scan --profile {core,extended}`, `profile` key in `cairnlock.toml` and
    `[tool.cairnlock]`, and a `profile` input in `action.yml`.
  - Profiles are exclusive; every rule id belongs to exactly one profile
    and rule ids are unchanged.
- Anti-false-positive mechanisms:
  - Inline suppression: `cairnlock:ignore` (all rules) or
    `cairnlock:ignore RULE1,RULE2` (selected rules) anywhere in a line.
  - All scans deduplicate findings with identical rule, path, line, and
    message, so one issue yields one finding.
- Anti-false-negative mechanisms:
  - SUP001 reads requirements files line by line; bare requirement names
    are flagged. The old pattern searched for the literal text
    "requirements.txt" inside lines and never matched real files.
  - Extended-profile discovery brings code and dependency files to the
    generic rules.
- Tests for per-profile finding counts, cross-profile exclusivity,
  duplicate detection, inline suppression, and discovery behavior.

### Changed

- MCP003 now flags shell and infrastructure commands as the MCP server
  executable (bash, sh, powershell, curl, wget, docker, podman, kubectl,
  helm) and no longer duplicates UNP001 on package runners. UNP001 covers
  npx, uvx, bunx, pnpm, yarn, and pipx, including `dlx`/`run` subcommands,
  so `pnpm dlx some-server` reports `some-server` instead of `dlx`.
- OBF001 no longer scans skill files (REM001's scope); the duplicated
  long-base64 finding is gone.
- CFG001 no longer scans markdown and text files, and its hardcoded-secret
  pattern was removed (SEC001 owns credentials); template prose no longer
  triggers findings.
- CRY001 hardcoded-key detection requires crypto-specific names
  (`secret_key`, `encryption_key`, `private_key`, `iv`, `nonce`, `salt`);
  plain `key =` assignments no longer duplicate SEC001.
- `cairnlock rules` shows a Profile column and per-rule scope.

## [0.4.0] - 2026-10-25

### Added

- Noise controls for adoption on large repositories:
  - `cairnlock.toml` (or `[tool.cairnlock]` in `pyproject.toml`) with
    `ignore` globs, `disabled_rules`, and a `fail_on` threshold.
  - `.cairnlockignore` with gitignore-style globs.
  - `scan --fail-on {low,medium,high,never}`: exit 1 only when a finding at
    or above the threshold exists. Exposed as the `fail-on` action input.
  - `scan --baseline <file>` and `--write-baseline`: known finding
    fingerprints are suppressed from reports and the exit decision.
  - The ASCII banner goes to stderr; JSON, SARIF, HTML, and Markdown output
    on stdout stay parseable. Regression tests cover this with the banner on.
- Discovery for more agent ecosystems, each with a fixture and a test:
  `.github/copilot-instructions.md`, `GEMINI.md`, `.windsurfrules`,
  `.clinerules` (file or directory), `.roo/**`, `.continue/**`,
  `.cursor/mcp.json`, `.vscode/mcp.json`, `.gemini/settings.json`,
  `claude_desktop_config.json`. Hidden agent directories (`.claude`,
  `.opencode`, `.cursor`, `.roo`, `.continue`, `.gemini`, `.vscode`,
  `.github`) are scanned; `.git`, `.venv`, and `node_modules` stay ignored.
  Fixes a discovery bug where files directly inside a hidden agent
  directory were never matched.
- PyPI packaging: complete project metadata, a release workflow
  (`.github/workflows/release.yml`) that builds, runs `twine check`, and
  publishes with PyPI trusted publishing (OIDC), and a version-consistency
  test between `pyproject.toml` and `cairnlock.__version__`.
- `docs/rules-audit.md`: rule-by-rule audit of scope, overlaps, and
  agent-specific versus generic classification, pending review.
- Redesigned ASCII banner: stacked CAIRN/LOCK block wordmark.

### Changed

- Install docs lead with `pipx install cairnlock` and `uvx cairnlock scan`;
  the git+https install stays as a fallback.
- Action description shortened below the 125-character marketplace limit.

## [0.3.0] - 2026-10-25

### Added

- `cairnlock verify --base <git-ref>`: reads `cairnlock.lock` as it exists at
  the given ref with `git show` and compares the working tree against it. A
  pull request that edits a tracked file and rehashes the lockfile in the
  same change now fails with "lockfile modified in this change".
- `--allow-lock-change` flag to permit lockfile-only changes.
- Exit code 2 for usage and environment errors in verify: refs starting with
  `-` are rejected before git runs, missing base lockfiles suggest running
  `cairnlock init` on the base branch, and shallow clones get a
  `fetch-depth: 0` hint for GitHub Actions.
- All git calls use an argument list, never a shell.
- `base-ref` and `allow-lock-change` inputs in `action.yml`, with a verify
  step that skips cleanly when no lockfile exists yet.
- Marketplace metadata in `action.yml` (name, description, branding).
- Documentation site in `docs/`: landing page, guide (lockfile workflow,
  base verification, CODEOWNERS, CI), and a full rule reference. Plain HTML,
  no build step.
- `docs/rules.md` as the SARIF helpUri target for every rule id.
- `SECURITY.md` with reporting instructions and scope.
- Dependabot config for pip and GitHub Actions.
- README section recommending CODEOWNERS protection for `cairnlock.lock`.

### Changed

- verify without a lockfile now exits 2 (usage/environment error) instead of 1.
- CLI status markers are plain text (`OK:`, `error:`, `warning:`) instead of
  emoji, per the project style rules.
- SARIF driver version now comes from the package version instead of a
  hard-coded string.
- Ruff ignores E501; long regex pattern tables and embedded report templates
  stay readable without manual line splitting.

### Fixed

- CI lint failures: `ruff check` passed locally on every configuration
  tested before this release.

## [0.2.0] - 2026-10-24

### Added
- `cairnlock scan` with 18 static detection rules:
  - HUC001: invisible and bidirectional Unicode control characters in instruction files
  - PIN001: prompt-injection phrases in tool and skill descriptions
  - REM001: pipe-to-shell downloads, base64 payloads, and remote fetches in skill files
  - MCP001: auto-approve or permission-skipping flags in MCP server configs
  - MCP002: MCP filesystem servers mounted at a filesystem root
  - MCP003: MCP server with unpinned dangerous command
  - MCP004: MCP server passed sensitive environment variable
  - UNP001: npx and uvx packages without a version pin
  - SEC001: embedded credentials in agent context files
  - SHC001: shell command execution patterns (eval, exec, subprocess, os.system)
  - NET001: suspicious network or data exfiltration patterns
  - FSY001: suspicious file system access (path traversal, sensitive files, archives)
  - ENV001: environment variable manipulation and credential access
  - PRI001: privilege escalation and process injection patterns
  - OBF001: encoding, obfuscation, and data hiding patterns
  - SUP001: supply chain attack risks in dependencies
  - CFG001: configuration and template injection vulnerabilities
  - TOO001: tool and function calling injection risks
  - CRY001: cryptographic weaknesses and insecure randomness
- Lockfile commands: `init`, `verify`, `diff`, `approve`
- Output formats: text, JSON, SARIF 2.1.0, HTML, Markdown
- New CLI commands: `rules` (list all rules), `stats` (repository statistics)
- Enhanced CLI UX: ASCII banner, colored output, progress bars, verbose mode
- Composite GitHub Action (`action.yml`) for CI and Code Scanning upload
- Example pre-commit hook in `hooks/`
- CI workflow running ruff and pytest on Python 3.11 and 3.13

### Changed
- Enhanced SARIF output with rule help URIs and partial fingerprints
- Improved embedded secret detection with Shannon entropy validation
- Expanded MCP config analysis with 4 rule IDs
- Refined supply chain detection for dependency confusion risks

### Fixed
- Secret detection false positives on placeholder values
- Cross-rule false positives in good fixtures

[Unreleased]: https://github.com/pennacle-security/cairnlock/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/pennacle-security/cairnlock/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/pennacle-security/cairnlock/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/pennacle-security/cairnlock/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pennacle-security/cairnlock/releases/tag/v0.2.0
