"""Kimi Chat tool — direct HTTP API access to kimi.moonshot.cn.

Registers a single ``kimi`` tool that uses browser_cookie3 to authenticate
and calls Kimi's internal API directly. Same pattern as gemini-cli.

Token efficiency: the tool writes the full response to a file and returns a tiny
JSON pointer (~50 tokens). The agent reads the file with read_file if needed.

Requirements (auto-detected via check_fn):
  - httpx installed in the agent venv
  - Valid Kimi auth (~/.kimi-cli/auth.json)
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

KIMI_SCRIPT = Path.home() / ".hermes" / "scripts" / "kimi" / "kimi.py"


def _find_python() -> str:
    venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return "python3"


KIMI_PY = _find_python()


def check_kimi_requirements() -> bool:
    if not KIMI_SCRIPT.exists():
        return False
    auth_file = Path.home() / ".kimi-cli" / "auth.json"
    if auth_file.exists():
        return True
    return False


def _kimi_tool(
    prompt: str,
    model: str = "kimi-k2",
    thinking: bool = True,
    conversation: str = "",
    fresh: bool = False,
    task_id: str | None = None,
) -> str:
    """Run a Kimi Chat query via direct HTTP API.

    Args:
        prompt: The text prompt to send to Kimi.
        model: kimi-k2 (default), kimi-k2-thinking, kimi-k1.5.
        thinking: Enable thinking mode. False = faster.
        conversation: Path to conversation state file for multi-turn chats.
        fresh: Start a fresh conversation.

    Returns:
        JSON string: {"ok": true, "f": "/tmp/...", "s": N, "b": N}
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tmpdir = Path(tempfile.gettempdir())
    out_file = tmpdir / f"kimi_{ts}.md"

    cmd = [
        KIMI_PY, str(KIMI_SCRIPT),
        "--no-thinking" if not thinking else "",
        "-m", model,
        "-o", str(out_file),
    ]
    if conversation:
        cmd.extend(["-c", conversation])
        if fresh:
            cmd.append("--new")

    cmd = [x for x in cmd if x]
    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            env={**os.environ},
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            err_detail = stderr or stdout or f"exit code {result.returncode}"
            if "no-auth" in stdout or "no-auth" in stderr:
                return json.dumps({
                    "ok": False, "err": "no-auth",
                    "msg": "Kimi auth not found. Log into https://www.kimi.com in Windows Firefox.",
                }, ensure_ascii=False)
            if "auth-expired" in stdout or "auth-expired" in stderr:
                return json.dumps({
                    "ok": False, "err": "auth-expired",
                    "msg": "Kimi session expired. Re-authenticate.",
                }, ensure_ascii=False)
            return json.dumps({
                "ok": False, "err": "error", "msg": err_detail[:500],
            }, ensure_ascii=False)

        # Parse the JSON pointer output from the CLI
        try:
            result_data = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            out_file.write_text(result.stdout.strip(), encoding="utf-8")
            size = out_file.stat().st_size
            code_blocks = result.stdout.count("```")
            result_data = {
                "ok": True, "f": str(out_file), "s": size, "b": code_blocks // 2,
            }

        return json.dumps(result_data, ensure_ascii=False)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "ok": False, "err": "timeout",
            "msg": "Kimi query timed out after 300 seconds.",
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({
            "ok": False, "err": "missing-python",
            "msg": f"Python not found at {KIMI_PY}. Is the venv intact?",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False, "err": "error", "msg": str(e)[:500],
        }, ensure_ascii=False)


KIMI_SCHEMA = {
    "name": "kimi",
    "description": (
        "Send a prompt to Kimi Chat (kimi.moonshot.cn) via browser-cookie "
        "authenticated HTTP API. Same pattern as gemini-cli — no browser "
        "automation needed. ~5-10s latency. "
        "\n\n"
        "CAPABILITIES: "
        "Text prompts, multi-turn conversations (use 'conversation' param), "
        "model switching (kimi-k2, kimi-k2-thinking, kimi-k1.5), "
        "thinking mode toggle. "
        "\n\n"
        "Returns a tiny JSON pointer — use read_file on 'f' to read the "
        "full response. This tool is faster than browser-based tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The text prompt to send to Kimi Chat.",
            },
            "model": {
                "type": "string",
                "description": (
                    "Model: kimi-k2 (default, latest), "
                    "kimi-k2-thinking (extended reasoning), "
                    "or kimi-k1.5 (legacy)."
                ),
                "enum": ["kimi-k2", "kimi-k2-thinking", "kimi-k1.5"],
                "default": "kimi-k2",
            },
            "thinking": {
                "type": "boolean",
                "description": "Enable thinking/reasoning mode. False = faster.",
                "default": True,
            },
            "conversation": {
                "type": "string",
                "description": (
                    "Path to conversation state file for multi-turn chats. "
                    "Use the SAME path across multiple kimi calls to maintain "
                    "context. Example: '/tmp/kimi_chat.json'."
                ),
            },
            "fresh": {
                "type": "boolean",
                "description": "Start a brand-new conversation. Only meaningful with 'conversation'.",
                "default": False,
            },
        },
        "required": ["prompt"],
    },
}


from tools.registry import registry

registry.register(
    name="kimi",
    toolset="kimi",
    schema=KIMI_SCHEMA,
    handler=lambda args, **kw: _kimi_tool(
        prompt=args.get("prompt", ""),
        model=args.get("model", "kimi-k2"),
        thinking=bool(args.get("thinking", True)),
        conversation=args.get("conversation", ""),
        fresh=bool(args.get("fresh", False)),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_kimi_requirements,
    emoji="🚀",
    max_result_size_chars=1000,
)
