"""Optional localhost browser console. Run: python -m windos.web.app --host 0.0.0.0 --port 8000"""
from __future__ import annotations
import argparse
import contextlib
import io
import secrets
import threading
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from windos.core import engine
from windos.core.auth import authenticate

app = FastAPI(title="WindOS Gateway", version="0.2.0")
_sessions = {}
_shells = {}
_lock = threading.RLock()

class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class CommandBody(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


def current_session(request: Request):
    token = request.cookies.get("windos_session")
    return _sessions.get(token), token

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(PAGE)

@app.post("/api/login")
def login(body: LoginBody, response: Response):
    user = authenticate(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = secrets.token_urlsafe(32)
    shell = engine.Shell()
    shell.load_state()
    shell.user = user
    shell.cwd = user.get("home", "/")
    _sessions[token] = user
    _shells[token] = shell
    response.set_cookie("windos_session", token, httponly=True, secure=False,
                        samesite="strict", max_age=8 * 60 * 60)
    return {"ok": True, "username": user["name"], "hostname": shell.cfg.get("hostname", "windos")}

@app.post("/api/logout")
def logout(request: Request, response: Response):
    _, token = current_session(request)
    if token:
        _sessions.pop(token, None)
        _shells.pop(token, None)
    response.delete_cookie("windos_session")
    return {"ok": True}

@app.post("/api/command")
def command(body: CommandBody, request: Request):
    user, token = current_session(request)
    if not user or not token or token not in _shells:
        raise HTTPException(status_code=401, detail="Please sign in again")
    line = body.command.strip()
    # The browser gateway is not a host-OS remote shell. Keep commands inside
    # the WindOS virtual environment and reject direct host execution.
    blocked = {"host", "exit", "logout", "quit", "shutdown", "poweroff", "reboot"}
    # Inspect every semicolon-separated command, not just the first one, so a
    # command chain cannot smuggle a host-shell request past the gateway.
    import shlex
    for part in line.split(";"):
        try:
            words = shlex.split(part)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid command quoting")
        if not words:
            continue
        first = words[0].lower()
        target = words[1].lower() if first == "sudo" and len(words) > 1 else first
        if target in blocked:
            raise HTTPException(status_code=403, detail="This command is unavailable in the browser gateway")
    shell = _shells[token]
    output = io.StringIO()
    with _lock, contextlib.redirect_stdout(output):
        try:
            shell.execute(line)
        except Exception as exc:
            print(f"WindOS error: {exc}")
    return {"output": output.getvalue(), "cwd": shell.short_cwd(),
            "username": user["name"], "hostname": shell.cfg.get("hostname", "windos")}

@app.get("/api/status")
def status(request: Request):
    user, token = current_session(request)
    if not user or token not in _shells:
        raise HTTPException(status_code=401, detail="Not signed in")
    shell = _shells[token]
    return {"username": user["name"], "hostname": shell.cfg.get("hostname", "windos"),
            "gamemode": bool(shell.cfg.get("gamemode")), "ram_mb": shell.ram_used(),
            "services_running": sum(1 for s in shell.svc.values() if s.get("running")),
            "services_total": len(shell.svc)}

PAGE = r'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>WindOS Gateway</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#e5e7eb;font:15px system-ui}main{max-width:1000px;margin:32px auto;padding:16px}.card{background:#111c2e;border:1px solid #29384f;border-radius:14px;padding:20px;margin-bottom:16px}h1{color:#60a5fa;margin-top:0}input,button{font:inherit;border-radius:8px;padding:11px;border:1px solid #334155}input{background:#07101d;color:white;width:100%;margin:6px 0}button{background:#2563eb;color:white;cursor:pointer;border:0}#terminal{height:55vh;overflow:auto;white-space:pre-wrap;background:#050b14;border-radius:9px;padding:14px;font:13px ui-monospace,monospace}#prompt{display:flex;gap:8px;margin-top:10px}#prompt input{flex:1}small{color:#94a3b8}.hidden{display:none}</style></head><body><main><section class="card"><h1>WindOS Gateway</h1><small>Browser console · authenticated session · virtual environment only</small></section>
<section id="login" class="card"><h2>Sign in</h2><input id="username" autocomplete="username" placeholder="Username"><input id="password" type="password" autocomplete="current-password" placeholder="Password"><button onclick="login()">Sign in</button><p id="loginerr"></p></section>
<section id="desk" class="hidden"><section class="card"><b id="identity"></b><span style="float:right" id="status"></span><button style="float:right;margin-right:12px" onclick="logout()">Log out</button></section><section class="card"><div id="terminal">Welcome to WindOS browser gateway. Type help to begin.\n</div><div id="prompt"><input id="cmd" placeholder="Enter a WindOS command" onkeydown="if(event.key==='Enter')run()"><button onclick="run()">Run</button></div></section></section></main>
<script>const $=id=>document.getElementById(id);async function api(path,data={}){let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let j=await r.json();if(!r.ok)throw Error(j.detail||'Request failed');return j}async function login(){try{let x=await api('/api/login',{username:$('username').value,password:$('password').value});$('login').classList.add('hidden');$('desk').classList.remove('hidden');$('identity').textContent=x.username+' @ '+x.hostname;$('password').value='';await status()}catch(e){$('loginerr').textContent=e.message}}async function run(){let c=$('cmd').value;$('cmd').value='';if(!c)return;let t=$('terminal');t.textContent+='$ '+c+'\n';try{let x=await api('/api/command',{command:c});t.textContent+=x.output;t.scrollTop=t.scrollHeight;await status()}catch(e){t.textContent+=e.message+'\n'}}async function status(){try{let s=await (await fetch('/api/status')).json();$('status').textContent='Game Mode '+(s.gamemode?'ON':'OFF')+' · '+s.services_running+'/'+s.services_total+' services · '+s.ram_mb+' MB'}catch(e){}}async function logout(){await api('/api/logout');$('desk').classList.add('hidden');$('login').classList.remove('hidden');$('terminal').textContent='Signed out.\n'}</script></body></html>'''

def main():
    import uvicorn
    parser = argparse.ArgumentParser(description="WindOS localhost web gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
