# Rule reference

SARIF results link here by rule id anchor. The rendered version lives at
`docs/rules.html`.

Rules run in one of two exclusive profiles. `core` (default) covers agent
context files; `extended` covers source and dependency files and widens
discovery to `.py`, `.js`, `.ts`, `requirements*`, `package.json`,
`pyproject.toml`, `setup.py`, and `setup.cfg`. One profile runs per scan.

| ID | Profile | Scope | Severity | Detects |
|---|---|---|---|---|
| [HUC001](#huc001) | core | all context files | high/medium/low | Invisible and bidirectional Unicode control characters |
| [PIN001](#pin001) | core | JSON description fields, SKILL.md frontmatter | high | Prompt-injection phrases in tool and skill descriptions |
| [REM001](#rem001) | core | SKILL.md, files under skills/ | high/medium | Pipe-to-shell downloads, base64 payloads, remote fetches |
| [MCP001](#mcp001) | core | MCP JSON configs | high | Auto-approve or permission-skipping flags |
| [MCP002](#mcp002) | core | MCP JSON configs | medium | Filesystem server mounted at a filesystem root |
| [MCP003](#mcp003) | core | MCP JSON configs | medium | Shell or infrastructure command as the server |
| [MCP004](#mcp004) | core | MCP JSON configs | high | Sensitive environment variables passed to a server |
| [CLD001](#cld001) | core | Claude Code settings.json | high | Risky permission allowlist: bare Bash, curl, bypassPermissions |
| [TAM001](#tam001) | core | all context files | high/medium | Agent context file attempts to defeat the scanner |
| [UNP001](#unp001) | core | MCP JSON configs | medium | Package-runner package without a version pin |
| [TOO001](#too001) | core | tool definitions, JSON configs | high/medium | Tool calling injection risks |
| [SEC001](#sec001) | extended | all scanned files | high/medium | Embedded credentials with entropy validation |
| [SHC001](#shc001) | extended | source files | high/medium | Shell command execution patterns |
| [NET001](#net001) | extended | source files | high/medium | Data exfiltration patterns |
| [FSY001](#fsy001) | extended | source files | high/medium | Path traversal, sensitive files, unsafe archives |
| [ENV001](#env001) | extended | source files | high/medium | Credential access through environment variables |
| [PRI001](#pri001) | extended | source files | high/medium | Privilege escalation and process injection |
| [OBF001](#obf001) | extended | source files, non-skill | high/medium/low | Encoding and obfuscation |
| [SUP001](#sup001) | extended | dependency files, non-skill | high/medium/low | Supply chain risks |
| [CFG001](#cfg001) | extended | structured config files, non-markdown | high/medium | Template and configuration injection |
| [CRY001](#cry001) | extended | source files | high/medium/low | Cryptographic weaknesses |

## HUC001 — hidden Unicode

Zero-width characters and bidirectional controls make rendered text differ
from what a parser or an agent reads. Bidirectional controls score high
because they enable Trojan Source style tricks. A UTF-8 BOM at byte zero is
not flagged.

## PIN001 — prompt injection

Matches injection phrases such as "ignore previous instructions" or "reveal
the system prompt" inside tool and skill description fields only.
Selected Indonesian phrases are also matched, including "abaikan semua
instruksi sebelumnya" and "ungkapkan prompt sistem". This is a phrase list,
so paraphrases and other languages can be missed; benign descriptions quoting
these phrases can trigger findings.

## REM001 — remote downloads in skills

curl or wget piped into a shell or interpreter, PowerShell
Invoke-Expression chains, base64 decode into a shell, certutil downloads,
long base64 literals, and remote git or pip sources inside skill files.

## MCP001 — auto-approve flags

`autoApprove: true` and permission-skipping flags such as
`--dangerously-skip-permissions`, `--yolo`, and `--no-auth`.

## MCP002 — filesystem root mounts

A filesystem server given `/`, `~`, or a drive root can read anything the
process can. Repo-relative mounts are fine.

## MCP003 — infrastructure commands as servers

Flags shell and infrastructure commands (bash, sh, powershell, curl, wget,
docker, podman, kubectl, helm) used as the MCP server executable, regardless
of arguments. Package runners belong to UNP001, so one issue yields one
finding.

## MCP004 — sensitive env vars

Server definitions that receive environment variables with credential-like
prefixes: cloud keys, database URLs, tokens, certificates.

## CLD001 — Claude Code permissions

Flags `permissions.allow` entries that grant an agent unrestricted shell
or network access (bare `Bash`, `Bash(curl:*)` and similar), and
`defaultMode: "bypassPermissions"`. Normal entries such as
`Bash(npm run test:*)` stay clean.

## UNP001 — unpinned packages

Package runners (npx, uvx, bunx, pnpm, yarn, pipx) execute whatever the
registry serves today. A pin such as `pkg@1.2.3` or `pkg==1.2.3` satisfies
the rule; `@latest` does not. Subcommands like `dlx` are skipped so the
package name is the one reported.

## SEC001 — embedded credentials

Provider formats (OpenAI, GitHub, Slack, AWS, Google, Bearer) score high.
Generic assignments require Shannon entropy above 3.5 so placeholders such
as `"changeme"` do not fire.

## SHC001 — shell command execution

String-form eval, exec, and compile, os.system, subprocess calls with shell
metacharacters or string formatting, and deprecated command modules.

## NET001 — exfiltration channels

Cloud metadata addresses, pastebin and webhook endpoints, tunneling
services, raw sockets, DNS resolution, HTTP calls carrying data payloads,
and long encoded fragments in URL paths.

## FSY001 — filesystem access

Traversal sequences, writes and deletes, SSH keys and certificates, env and
secrets files, and archive extraction with zip-slip risk.

## ENV001 — credential access

Iteration, serialization, printing, or logging of the whole environment,
direct reads of cloud and database variables, and shell expansions of long
uppercase variables.

## PRI001 — escalation and injection

Docker and Kubernetes privileged modes, host namespace sharing, docker
socket access, LD_PRELOAD, ptrace attach, Windows registry run keys,
scheduled tasks, and encoded PowerShell.

## OBF001 — obfuscation

Base64 round trips combined with compression, PowerShell encoded commands,
XOR ciphers, long encoded literals, and Cyrillic, Greek, or fullwidth
homoglyphs.

## SUP001 — supply chain

Unpinned installs, wildcard versions, git-sourced dependencies, custom
package indexes, and install-time scripts in package definitions.

## CFG001 — config and template injection

Template delimiters, unsafe YAML python tags, dunder references in config,
and connection strings with inline credentials. Runs on structured config
files only, not markdown, where template prose would false-positive.
Credential assignments belong to SEC001.

## TOO001 — tool calling

Tools named shell, exec, or similar; descriptions that advertise arbitrary
execution; autonomous agent frameworks; disabled strict mode.

## TAM001 — self-tamper

An agent context file instructing the agent to run `cairnlock approve`,
delete or revert the lockfile, disable the scanner, or add
`cairnlock:ignore` suppressions is asking the agent to defeat the guard.
Ordinary documentation about the tool stays clean.

## CRY001 — cryptography

MD5 and SHA1, DES and RC4, AES-ECB, RSA keys at 1024 bits or below, the
random module for security purposes, disabled certificate verification, and
hardcoded keys or IVs.
