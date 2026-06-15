#!/usr/bin/env python3
"""Kimi CLI — Firefox cookie fallback. Uses Playwright with injected Firefox cookies."""

import os, sys, json, time, argparse, sqlite3, shutil
from pathlib import Path

HOME = Path.home()
BASE = "https://www.kimi.com"
_Q = False

def fail(c,r): print(json.dumps({"ok":False,"err":c,"msg":r},ensure_ascii=False)); sys.exit(1)
def log(m): print(m,file=sys.stderr,flush=True)
def info(m):
    if not _Q and sys.stderr.isatty(): print(f"[kimi] {m}",file=sys.stderr)

def extract_firefox_cookies():
    best = {}
    for ud in Path("/mnt/c/Users").iterdir():
        if not ud.is_dir(): continue
        fp = ud / "AppData/Roaming/Mozilla/Firefox/Profiles"
        if not fp.exists(): continue
        for p in fp.iterdir():
            if not (p/"cookies.sqlite").exists(): continue
            try:
                t = Path(f"/tmp/kf_{os.getpid()}.sqlite")
                shutil.copy2(str(p/"cookies.sqlite"),str(t))
                c = sqlite3.connect(str(t)); cur = c.cursor()
                cur.execute("SELECT name,value,host FROM moz_cookies WHERE host LIKE '%kimi%' OR host LIKE '%moonshot%'")
                rows = cur.fetchall(); c.close(); t.unlink(missing_ok=True)
                if len(rows) > len(best):
                    best = [(n,v.strip('"'),h) for n,v,h in rows]
            except: pass
    return best

def extract_response(body):
    lines = body.split('\n')
    last = -1
    for i in range(len(lines)-1,-1,-1):
        if lines[i].strip() == 'Share': last = i; break
    if last < 0: return ''
    thinking = ('Thinking','Thought for','Decide','Retrieve','Add ','Confirm',
                'Looking','The user','I need','I should','I can','But ',
                'However','Actually','Wait','Let me','Memory')
    cands = []
    for i in range(last+1,len(lines)):
        line = lines[i].strip()
        if not line: continue
        if line=="Throw me a hard one. I'm ready." or 'K2.6' in line: break
        cands.append(line)
    for i in range(len(cands)-1,-1,-1):
        line = cands[i]
        if len(line)>200 or line=='Thinking' or any(line.startswith(p) for p in thinking): continue
        return line
    return cands[-1] if cands else ''

def kimi_chat(prompt):
    from playwright.sync_api import sync_playwright
    cookies = extract_firefox_cookies()
    if not cookies: raise Exception("No Kimi cookies")
    
    with sync_playwright() as pw:
        ctx = pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-gpu'])
        context = ctx.new_context(viewport={'width':1280,'height':800})
        for n,v,domain in cookies:
            d = domain if domain.startswith('.') else f'.{domain}'
            context.add_cookies([{'name':n,'value':v,'domain':d,'path':'/',
                'httpOnly':False,'secure':True,'sameSite':'Lax'}])
        pg = context.new_page()
        pg.goto(BASE, wait_until='networkidle',timeout=30000)
        time.sleep(4)
        
        pre = pg.locator('body').inner_text().count('Share')
        editor = pg.locator('[contenteditable="true"]').first
        if editor.count()==0: raise Exception("no-input")
        editor.click(); time.sleep(0.5)
        editor.fill(prompt); time.sleep(0.5)
        editor.press('Enter'); time.sleep(1)
        
        text = ""; deadline = time.time()+120
        while time.time()<deadline:
            body = pg.locator('body').inner_text()
            if body.count('Share') > pre:
                time.sleep(2)
                text = extract_response(pg.locator('body').inner_text())
                if text: break
            time.sleep(0.5)
        context.close(); ctx.close()
        return text

def main():
    global _Q
    p = argparse.ArgumentParser(description="Kimi Web CLI (Firefox fallback)")
    p.add_argument("prompt",nargs="*"); p.add_argument("-p","--prompt-flag")
    p.add_argument("-o","--output"); p.add_argument("--json",action="store_true")
    p.add_argument("-q","--quiet",action="store_true")
    args = p.parse_args()
    if args.quiet: _Q = True
    
    prompt = args.prompt_flag or (" ".join(args.prompt) if args.prompt else None)
    if not prompt and not sys.stdin.isatty(): prompt = sys.stdin.read().strip()
    if not prompt: p.print_help(); sys.exit(1)
    
    try:
        text = kimi_chat(prompt)
        log("[KIMI:DONE]")
        if args.output:
            op = Path(args.output); op.write_text(text,encoding="utf-8")
            print(json.dumps({"f":str(op),"s":op.stat().st_size,"b":text.count("```")//2},ensure_ascii=False))
        elif args.json:
            print(json.dumps({"ok":True,"text":text},ensure_ascii=False))
        else:
            print(text)
    except Exception as e:
        fail("error",str(e))

if __name__=="__main__":
    try: main()
    except SystemExit: raise
    except Exception as e: fail("error",str(e))
