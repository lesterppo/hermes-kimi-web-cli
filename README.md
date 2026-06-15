# Hermes Kimi Web CLI

CLI for Kimi (kimi.com) via Playwright browser automation. No API key needed. Designed as a native tool for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

## Quick Start

```bash
# Login to kimi.com in Chrome, then:
export KIMI_CHROME_PROFILE="/mnt/c/Users/YOU/AppData/Local/Google/Chrome/User Data"
python kimi.py "Hello, Kimi!"
```

## Features

- **Zero API cost** — uses your Chrome browser session
- **Token-efficient** — returns `{"f":"/tmp/out.md","s":N,"b":N}` (~45 chars)
- **Multi-turn** — `-c chat.json` for conversation continuity
- **Model switching** — `-m kimi-k2`, `-m kimi-k1.5`
- **Multi-account** — auto-switches on rate limits
- **Auto Chrome detection** — finds Chrome profile automatically on WSL

## Installation

```bash
pip install playwright httpx
playwright install chromium
```

Set `KIMI_CHROME_PROFILE` env var or let it auto-detect from `/mnt/c/Users/*/`.

## Hermes Integration

```bash
cp kimi_tool.py ~/.hermes/hermes-agent/tools/
# Add "kimi" to _HERMES_CORE_TOOLS in toolsets.py
```

## Files

| File | Purpose |
|------|---------|
| `kimi.py` | Main CLI (Chrome profile sync) |
| `kimi_firefox_fallback.py` | Standalone Firefox cookie injection |
| `kimi_tool.py` | Native Hermes Agent tool |

## Architecture

```
Chrome User Data → Playwright persistent context → kimi.com web UI
                                               → [contenteditable] input
                                               → Share button detection
                                               → Python text extraction
```
