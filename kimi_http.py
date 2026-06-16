#!/usr/bin/env python3
"""
Fast Kimi CLI via HTTP API (Bearer token auth). No browser, no EPIPE, ~3-5s.
Replaces the Playwright-based kimi.py when auth is available.

Usage:
  python kimi_http.py "prompt"
  python kimi_http.py -o /tmp/out.md "prompt"
"""

import os, sys, json, time, argparse, sqlite3, shutil, uuid
from pathlib import Path

HOME = Path.home()
DIR = HOME / ".kimi-cli"
AUTH_FILE = DIR / "auth_http.json"
BASE = "https://www.kimi.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_Q = False

def log(m): print(m, file=sys.stderr, flush=True)
def fail(c, r): print(json.dumps({"ok": False, "err": c, "msg": r}, ensure_ascii=False)); sys.exit(1)


def extract_jwt():
    """Extract kimi-auth JWT from Windows Firefox profiles."""
    # Check env var first
    env_jwt = os.environ.get("KIMI_JWT", "")
    if env_jwt:
        return env_jwt
    
    # Check saved auth
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text()).get("jwt", "")
        except:
            pass
    
    # Scan Firefox profiles
    for ud in Path("/mnt/c/Users").iterdir():
        if not ud.is_dir(): continue
        fp = ud / "AppData/Roaming/Mozilla/Firefox/Profiles"
        if not fp.exists(): continue
        for p in fp.iterdir():
            if not (p / "cookies.sqlite").exists(): continue
            try:
                t = Path(f"/tmp/kj_{os.getpid()}.sqlite")
                shutil.copy2(str(p / "cookies.sqlite"), str(t))
                c = sqlite3.connect(str(t))
                cur = c.cursor()
                cur.execute("SELECT value FROM moz_cookies WHERE name='kimi-auth' AND host LIKE '%kimi%'")
                row = cur.fetchone()
                c.close(); t.unlink(missing_ok=True)
                if row:
                    jwt = row[0]
                    DIR.mkdir(parents=True, exist_ok=True)
                    AUTH_FILE.write_text(json.dumps({"jwt": jwt, "saved_at": time.time()}))
                    return jwt
            except:
                pass
    return ""


def kimi_chat(prompt: str, model: str = "kimi-k2") -> str:
    """Send prompt via Kimi HTTP API with SSE streaming."""
    import httpx
    
    jwt = extract_jwt()
    if not jwt:
        raise RuntimeError("No Kimi JWT. Log into kimi.com in Firefox first.")
    
    headers = {
        "authorization": f"Bearer {jwt}",
        "user-agent": UA,
        "content-type": "application/json",
        "origin": BASE, "referer": f"{BASE}/",
        "accept": "text/event-stream",
    }
    
    chat_id = str(uuid.uuid4()).replace("-", "")[:20]
    
    r = httpx.post(f"{BASE}/api/chat", headers=headers, timeout=60,
        json={
            "name": prompt[:50].split("\n")[0].strip(),
            "is_new": True,
            "messages": [{"role": "user", "content": prompt}],
            "chat_id": chat_id,
        })
    
    if r.status_code == 401:
        # JWT expired — delete cached auth
        AUTH_FILE.unlink(missing_ok=True)
        raise RuntimeError("auth-expired")
    if r.status_code != 200:
        raise RuntimeError(f"API {r.status_code}: {r.text[:200]}")
    
    text = ""
    for line in r.iter_lines():
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:].strip())
                # Kimi SSE: {"text": "chunk"} or {"content": "..."}
                if "text" in d:
                    text += d["text"]
                elif "content" in d:
                    text += d["content"]
                elif "choices" in d:
                    text += d["choices"][0].get("delta", {}).get("content", "")
                elif "delta" in d:
                    text += d.get("delta", {}).get("content", "")
            except json.JSONDecodeError:
                pass
    
    text = text.strip()
    if not text:
        raise RuntimeError("empty-response")
    return text


def main():
    global _Q
    p = argparse.ArgumentParser(description="Kimi HTTP API CLI (~3-5s)")
    p.add_argument("prompt", nargs="*")
    p.add_argument("-p", "--prompt-flag")
    p.add_argument("-o", "--output")
    p.add_argument("--json", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("--save-jwt", action="store_true", help="Save JWT from Firefox")
    args = p.parse_args()
    if args.quiet: _Q = True
    
    if args.save_jwt:
        jwt = extract_jwt()
        if jwt:
            print(f"JWT saved ({len(jwt)} chars)")
        else:
            print("No JWT found. Log into kimi.com in Firefox first.")
        return
    
    prompt = args.prompt_flag or (" ".join(args.prompt) if args.prompt else None)
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        p.print_help(); sys.exit(1)
    
    log("[KIMI:API]")
    try:
        text = kimi_chat(prompt)
    except Exception as e:
        fail("error", str(e))
    
    log("[KIMI:DONE]")
    
    if args.output:
        op = Path(args.output)
        op.write_text(text, encoding="utf-8")
        print(json.dumps({"f": str(op), "s": op.stat().st_size, "b": text.count("```") // 2}, ensure_ascii=False))
    elif args.json:
        print(json.dumps({"ok": True, "text": text}, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()
