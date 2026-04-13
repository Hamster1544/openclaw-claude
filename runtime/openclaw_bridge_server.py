#!/opt/openclaw-bridge/venv/bin/python
import json,mimetypes,os,subprocess,sys,time,uuid
from pathlib import Path
import requests
from mcp.server.fastmcp import FastMCP

mcp=FastMCP("openclaw_bridge")
BOT_TOKEN=os.environ.get("OPENCLAW_TG_BOT_TOKEN","").strip()
TARGET_CHAT=os.environ.get("OPENCLAW_TARGET_TO","").strip()
TARGET_TO_RAW=os.environ.get("OPENCLAW_TARGET_TO_RAW","").strip()
CHANNEL=os.environ.get("OPENCLAW_TARGET_CHANNEL","telegram").strip() or "telegram"
GATEWAY_URL=os.environ.get("OPENCLAW_GATEWAY_URL","").strip()
GATEWAY_TOKEN=os.environ.get("OPENCLAW_GATEWAY_TOKEN","").strip()
CURRENT_AGENT_ID=os.environ.get("OPENCLAW_CURRENT_AGENT_ID","main").strip() or "main"
CURRENT_SESSION_KEY=os.environ.get("OPENCLAW_CURRENT_SESSION_KEY","").strip()
ALLOW_ANY=os.environ.get("OPENCLAW_ALLOW_ANY_AGENTS","false").lower() in {"1","true","yes","on"}
DELIVERY=json.loads(os.environ.get("OPENCLAW_DELIVERY_CONTEXT_JSON") or "{}")
KNOWN=[x for x in json.loads(os.environ.get("OPENCLAW_KNOWN_AGENTS_JSON") or "[]") if isinstance(x,dict)]
ALLOWED=[str(x).strip().lower() for x in json.loads(os.environ.get("OPENCLAW_ALLOWED_AGENT_IDS_JSON") or "[]") if str(x).strip()]
BIN="/usr/bin/openclaw"
WATCH="--watch-subagent"
STATE=Path("/root/.openclaw")
CONFIG=STATE/"openclaw.json"
RELAY="/usr/local/bin/claude-openclaw-relay"
DEFAULT_WORKSPACE="/home/openclaw/workspace"

def now_ms():
    return int(time.time()*1000)

def _sudo_py(code, payload, timeout=45):
    proc=subprocess.run([
        "/usr/bin/sudo","-n","/usr/bin/python3","-c",code
    ], input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True, timeout=timeout)
    if proc.returncode!=0:
        raise RuntimeError((proc.stderr or proc.stdout or "sudo python failed").strip())
    return proc.stdout

def load_json(path, default):
    p=Path(path)
    try:
        if str(p).startswith("/root/"):
            raw=_sudo_py(
                "import json,sys; from pathlib import Path; req=json.load(sys.stdin); p=Path(req['path']);\n"
                "try:\n data=json.loads(p.read_text())\n"
                "except Exception:\n data=req['default']\n"
                "json.dump(data if data is not None else req['default'], sys.stdout, ensure_ascii=False)",
                {"path": str(p), "default": default},
            )
            data=json.loads(raw) if raw.strip() else default
        else:
            data=json.loads(p.read_text())
        return data if data is not None else default
    except Exception:
        return default

def save_json_atomic(path, value):
    p=Path(path)
    if str(p).startswith("/root/"):
        _sudo_py(
            "import json,sys,os; from pathlib import Path; req=json.load(sys.stdin); p=Path(req['path']); p.parent.mkdir(parents=True, exist_ok=True); tmp=p.with_name(p.name + '.tmp.' + req['suffix']); tmp.write_text(json.dumps(req['value'], ensure_ascii=False, indent=2)); os.replace(tmp, p)",
            {"path": str(p), "value": value, "suffix": uuid.uuid4().hex},
        )
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp=p.with_name(f"{p.name}.tmp.{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(tmp, p)

def cfg():
    return load_json(CONFIG, {})

def agent_entry(agent_id):
    data=cfg()
    for entry in ((data.get("agents") or {}).get("list") or []):
        if isinstance(entry,dict) and str(entry.get("id") or "").strip().lower()==agent_id:
            return entry
    return {}

def workspace_for(agent_id):
    data=cfg()
    defaults=((data.get("agents") or {}).get("defaults") or {})
    entry=agent_entry(agent_id)
    value=str(entry.get("workspace") or defaults.get("workspace") or DEFAULT_WORKSPACE).strip()
    return value or DEFAULT_WORKSPACE

def model_for(agent_id):
    data=cfg()
    defaults=((data.get("agents") or {}).get("defaults") or {})
    entry=agent_entry(agent_id)
    model=((entry.get("model") or {}).get("primary") if isinstance(entry.get("model"),dict) else entry.get("model"))
    if not model:
        model=((defaults.get("model") or {}).get("primary") if isinstance(defaults.get("model"),dict) else defaults.get("model"))
    model=str(model or "claude-cli/claude-sonnet-4-6").strip()
    return model.split("/",1)[1] if "/" in model else model

def session_store(agent_id):
    return STATE/"agents"/agent_id/"sessions"/"sessions.json"

def load_sessions(agent_id):
    data=load_json(session_store(agent_id), {})
    return data if isinstance(data,dict) else {}

def save_sessions(agent_id, sessions):
    save_json_atomic(session_store(agent_id), sessions)

def pick_template_session(agent_id):
    items=[(k,v) for k,v in load_sessions(agent_id).items() if isinstance(v,dict)]
    items.sort(key=lambda kv: kv[1].get("updatedAt",0), reverse=True)
    for key,entry in items:
        if ":subagent:" not in key:
            return key,entry
    return items[0] if items else (None,{})

def seed_session(agent_id, child_key, cli_session_id, label, spawned_by):
    sessions=load_sessions(agent_id)
    _,template=pick_template_session(agent_id)
    entry={
        "sessionId": str(uuid.uuid4()),
        "updatedAt": now_ms(),
        "label": label or None,
        "spawnedBy": spawned_by or None,
        "claudeCliSessionId": cli_session_id,
        "cliSessionIds": {"claude-cli": cli_session_id},
        "systemSent": bool(template.get("systemSent", True)),
        "modelProvider": template.get("modelProvider") or "claude-cli",
        "model": template.get("model") or model_for(agent_id),
    }
    for key in ("skillsSnapshot","deliveryContext","origin","channel","lastChannel","lastTo","lastAccountId","sessionFile"):
        if key in template and template.get(key) is not None:
            entry[key]=template.get(key)
    if not entry.get("deliveryContext"):
        delivery_to=str((DELIVERY.get("to") or TARGET_TO_RAW or "")).strip()
        delivery_channel=str((DELIVERY.get("channel") or CHANNEL or "telegram")).strip() or "telegram"
        if delivery_to:
            entry["deliveryContext"]={
                "channel": delivery_channel,
                "to": delivery_to,
                "accountId": str(DELIVERY.get("accountId") or "default").strip() or "default",
            }
            if DELIVERY.get("threadId"):
                entry["deliveryContext"]["threadId"]=str(DELIVERY.get("threadId"))
    if not entry.get("origin"):
        delivery_to=str((DELIVERY.get("to") or TARGET_TO_RAW or "")).strip()
        delivery_channel=str((DELIVERY.get("channel") or CHANNEL or "telegram")).strip() or "telegram"
        if delivery_to:
            entry["origin"]={
                "provider": delivery_channel,
                "surface": delivery_channel,
                "channel": delivery_channel,
                "from": delivery_to,
                "to": delivery_to,
                "label": delivery_to,
            }
    if not entry.get("channel"):
        entry["channel"]=str((DELIVERY.get("channel") or CHANNEL or "telegram")).strip() or "telegram"
    if not entry.get("lastChannel"):
        entry["lastChannel"]=entry.get("channel")
    if not entry.get("lastTo"):
        entry["lastTo"]=str((DELIVERY.get("to") or TARGET_TO_RAW or "")).strip() or entry.get("lastTo")
    if not entry.get("lastAccountId") and DELIVERY.get("accountId"):
        entry["lastAccountId"]=str(DELIVERY.get("accountId"))
    sessions[child_key]=entry
    save_sessions(agent_id, sessions)
    return entry

def update_session_result(agent_id, child_key, result=None, error=None):
    sessions=load_sessions(agent_id)
    entry=sessions.get(child_key) or {}
    entry["updatedAt"]=now_ms()
    if result:
        entry["claudeCliSessionId"]=result.get("session_id") or entry.get("claudeCliSessionId")
        entry["cliSessionIds"]={"claude-cli": entry.get("claudeCliSessionId")}
        usage=result.get("usage") or {}
        entry["inputTokens"]=usage.get("input_tokens")
        entry["outputTokens"]=usage.get("output_tokens")
        entry["contextTokens"]=(usage.get("cache_read_input_tokens") or 0)+(usage.get("cache_creation_input_tokens") or 0)
        total=(usage.get("input_tokens") or 0)+(usage.get("output_tokens") or 0)+(usage.get("cache_read_input_tokens") or 0)+(usage.get("cache_creation_input_tokens") or 0)
        entry["totalTokens"]=total
        entry["abortedLastRun"]=False
    if error:
        entry["abortedLastRun"]=True
    sessions[child_key]=entry
    save_sessions(agent_id, sessions)

def delete_session(agent_id, child_key):
    sessions=load_sessions(agent_id)
    if child_key in sessions:
        sessions.pop(child_key, None)
        save_sessions(agent_id, sessions)

def get_session_entry(agent_id, child_key):
    sessions=load_sessions(agent_id)
    entry=sessions.get(child_key)
    return entry if isinstance(entry, dict) else {}

def mark_direct_delivery(kind="text", agent_id=None, child_key=None):
    agent_id=(agent_id or CURRENT_AGENT_ID or "main").strip().lower() or "main"
    child_key=(child_key or CURRENT_SESSION_KEY or "").strip()
    if ":subagent:" not in child_key:
        return
    sessions=load_sessions(agent_id)
    entry=sessions.get(child_key)
    if not isinstance(entry, dict):
        return
    meta=entry.get("bridgeDelivery") or {}
    meta["count"]=int(meta.get("count") or 0)+1
    meta["lastKind"]=str(kind or "text")
    meta["lastAt"]=now_ms()
    entry["bridgeDelivery"]=meta
    entry["updatedAt"]=now_ms()
    sessions[child_key]=entry
    save_sessions(agent_id, sessions)

def has_direct_delivery(agent_id, child_key):
    meta=(get_session_entry(agent_id, child_key).get("bridgeDelivery") or {})
    return int(meta.get("count") or 0) > 0

def tg_need():
    if CHANNEL!="telegram" or not BOT_TOKEN or not TARGET_CHAT:
        raise RuntimeError("telegram bridge env missing")
    return BOT_TOKEN,TARGET_CHAT

def tg(method,data,files=None):
    token,_=tg_need()
    r=requests.post(f"https://api.telegram.org/bot{token}/{method}",data=data,files=files,timeout=120)
    r.raise_for_status()
    payload=r.json()
    if not payload.get("ok"):
        raise RuntimeError(str(payload))
    return payload["result"]

def gw(method,params=None,expect=False,timeout=30000):
    cmd=["/usr/bin/sudo","-n",BIN,"gateway","call",method,"--json","--timeout",str(max(1000,int(timeout))),"--params",json.dumps(params or {},ensure_ascii=False)]
    if expect:
        cmd.append("--expect-final")
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=max(30,int(timeout/1000)+15))
    if p.returncode!=0:
        raise RuntimeError((p.stderr or p.stdout or "gateway call failed").strip())
    raw=(p.stdout or "").strip()
    return json.loads(raw) if raw else {}

def allow(agent_id):
    target=(agent_id or CURRENT_AGENT_ID).strip().lower() or CURRENT_AGENT_ID
    cur=CURRENT_AGENT_ID.strip().lower() or "main"
    if target==cur or ALLOW_ANY or target in ALLOWED:
        return target
    raise RuntimeError(f"agentId not allowed from {cur}: {target}")

def send_back(text):
    text=(text or "").strip()
    if not text:
        return
    params={"channel":str(DELIVERY.get("channel") or CHANNEL or "telegram"),"to":str(DELIVERY.get("to") or TARGET_TO_RAW or "").strip(),"message":text,"idempotencyKey":str(uuid.uuid4())}
    if DELIVERY.get("accountId"):
        params["accountId"]=DELIVERY["accountId"]
    if DELIVERY.get("threadId"):
        params["threadId"]=str(DELIVERY["threadId"])
    try:
        gw("send",params,timeout=15000)
    except Exception:
        if TARGET_CHAT and CHANNEL=="telegram":
            tg("sendMessage",{"chat_id":TARGET_CHAT,"text":text,"disable_notification":"false"})
        else:
            raise

def spawn_watch(payload):
    env=os.environ.copy()
    env["OPENCLAW_SUBAGENT_WATCH_PAYLOAD"]=json.dumps(payload,ensure_ascii=False)
    subprocess.Popen([sys.executable,__file__,WATCH],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True)

def parse_claude_result(stdout):
    for line in reversed((stdout or "").splitlines()):
        line=line.strip()
        if not line:
            continue
        try:
            data=json.loads(line)
        except Exception:
            continue
        if isinstance(data,dict) and data.get("type")=="result":
            return data
    return None

def short_error(stdout, stderr):
    text=(stderr or "").strip() or (stdout or "").strip()
    if not text:
        return "background run failed"
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:500] if lines else "background run failed"

def build_runtime_prompt(agent_id, child_key, task, spawned_by):
    _,template=pick_template_session(agent_id)
    skills=((template.get("skillsSnapshot") or {}).get("prompt") or "").strip()
    workspace=workspace_for(agent_id)
    parts=[
        "You are a personal assistant running inside OpenClaw.",
        "Claude Code native tools are available in this session. An MCP bridge named openclaw_bridge is also available for the current OpenClaw session.",
        "Use openclaw_bridge.session_context to inspect routing context, openclaw_bridge.send_text to send an extra text message, and openclaw_bridge.send_file to send a local file directly into the current Telegram chat.",
        "Use openclaw_bridge.agents_list to discover configured agents. sessions_spawn is disabled from subagent sessions.",
        f"Workspace: {workspace}",
        "",
        "# Subagent Context",
        f"- Agent id: {agent_id}",
        f"- Task: {' '.join(task.split())}",
        f"- Requester session: {spawned_by or '(none)'}",
        f"- Your session: {child_key}",
        "- Stay focused and complete only this task.",
        "- For long-running shell, apt, docker, or network work, send a short progress update first.",
        "- If you deliver the final result directly to Telegram with openclaw_bridge.send_text or send_file, do it once unless length limits force a split.",
        "- After a direct Telegram delivery, do not repeat the same full content in your final assistant reply; return only a short status like DELIVERED.",
        "",
        "# Workspace Bootstrap",
        "Before doing substantial work, read AGENTS.md, SOUL.md, USER.md, and today's memory file if they exist in the workspace.",
    ]
    if agent_id=="main":
        parts.append("Because this is the main agent, also read MEMORY.md if it exists.")
    if skills:
        parts.extend(["","# Skills Snapshot",skills])
    parts.extend(["","Tools are disabled in this session. Do not call tools."])
    return "\n".join(parts).strip()

def run_direct_subagent(payload):
    agent_id=str(payload.get("agentId") or "main").strip().lower() or "main"
    child_key=str(payload["childSessionKey"])
    cli_session_id=str(payload["cliSessionId"])
    task=str(payload["task"] or "").strip()
    workspace=str(payload.get("workspace") or workspace_for(agent_id)).strip() or DEFAULT_WORKSPACE
    system_prompt=str(payload.get("systemPrompt") or "").strip()
    model=str(payload.get("model") or model_for(agent_id)).strip() or "claude-sonnet-4-6"
    timeout_seconds=int(payload.get("runTimeoutSeconds") or 0)
    env=os.environ.copy()
    env["OPENCLAW_CURRENT_AGENT_ID"]=agent_id
    env["OPENCLAW_CURRENT_SESSION_KEY"]=child_key
    cmd=["/usr/bin/sudo","-n","/usr/bin/env",f"OPENCLAW_CURRENT_AGENT_ID={agent_id}",f"OPENCLAW_CURRENT_SESSION_KEY={child_key}",RELAY,"-p","--output-format","json","--dangerously-skip-permissions","--model",model,"--session-id",cli_session_id,"--append-system-prompt",system_prompt,task]
    try:
        proc=subprocess.run(cmd,cwd=workspace if os.path.isdir(workspace) else DEFAULT_WORKSPACE,env=env,text=True,capture_output=True,timeout=(timeout_seconds+60) if timeout_seconds>0 else None)
    except subprocess.TimeoutExpired:
        update_session_result(agent_id, child_key, error="timeout")
        return False, f"{payload.get('label') or agent_id or 'subagent'} failed: timed out"
    result=parse_claude_result(proc.stdout)
    if proc.returncode==0 and result and not result.get("is_error"):
        update_session_result(agent_id, child_key, result=result)
        reply=str(result.get("result") or "").strip()
        tag=(payload.get("label") or agent_id or "subagent").strip()
        body=reply or f"{tag} completed."
        if tag and reply and not body.startswith(f"[{tag}]"):
            body=f"[{tag}] {body}"
        return True, body
    update_session_result(agent_id, child_key, error=short_error(proc.stdout, proc.stderr))
    tag=(payload.get("label") or agent_id or "subagent").strip()
    return False, f"{tag} failed: {short_error(proc.stdout, proc.stderr)}"

def watch():
    payload=json.loads(os.environ.get("OPENCLAW_SUBAGENT_WATCH_PAYLOAD") or "{}")
    ok,body=run_direct_subagent(payload)
    agent_id=str(payload.get("agentId") or "main").strip().lower() or "main"
    child_key=str(payload.get("childSessionKey") or "")
    delivered=has_direct_delivery(agent_id, child_key)
    if (not ok) or (not delivered):
        send_back(body)
    if str(payload.get("cleanup") or "keep").lower()=="delete":
        delete_session(agent_id, child_key)
    return 0 if ok else 1

@mcp.tool()
def session_context():
    return {"channel":CHANNEL,"chat_id":TARGET_CHAT,"to":TARGET_TO_RAW or None,"current_agent_id":CURRENT_AGENT_ID,"current_session_key":CURRENT_SESSION_KEY or None}

@mcp.tool()
def agents_list():
    cur=(CURRENT_AGENT_ID or "main").strip().lower() or "main"
    by={str(x.get("id") or "").strip().lower():x for x in KNOWN}
    ids={cur}
    ids.update(by.keys() if ALLOW_ANY else ALLOWED)
    return {"requester":cur,"allowAny":ALLOW_ANY,"agents":[{"id":agent_id,"name":by.get(agent_id,{}).get("name"),"configured":bool(by.get(agent_id,{}).get("configured",bool(by.get(agent_id))))} for agent_id in [cur,*sorted(x for x in ids if x!=cur)]]}

@mcp.tool()
def sessions_spawn(task:str,agent_id:str="",label:str="",run_timeout_seconds:int=0,cleanup:str="keep"):
    if not (task or "").strip():
        raise ValueError("task must be non-empty")
    if ":subagent:" in CURRENT_SESSION_KEY:
        raise RuntimeError("sessions_spawn is not allowed from sub-agent sessions")
    target=allow(agent_id)
    child=f"agent:{target}:subagent:{uuid.uuid4()}"
    cli_session_id=str(uuid.uuid4())
    watcher_run_id=str(uuid.uuid4())
    seed_session(target, child, cli_session_id, label.strip(), CURRENT_SESSION_KEY or None)
    payload={
        "mode":"direct",
        "runId": watcher_run_id,
        "agentId": target,
        "childSessionKey": child,
        "cliSessionId": cli_session_id,
        "label": label.strip(),
        "cleanup": cleanup or "keep",
        "task": task.strip(),
        "workspace": workspace_for(target),
        "model": model_for(target),
        "runTimeoutSeconds": int(run_timeout_seconds or 0),
        "systemPrompt": build_runtime_prompt(target, child, task.strip(), CURRENT_SESSION_KEY or None),
    }
    spawn_watch(payload)
    return {"status":"accepted","run_id":watcher_run_id,"child_session_key":child,"agent_id":target,"label":label.strip() or None,"cleanup":cleanup or "keep"}

@mcp.tool()
def send_text(text:str,disable_notification:bool=False):
    _,chat=tg_need()
    if not (text or "").strip():
        raise ValueError("text must be non-empty")
    result=tg("sendMessage",{"chat_id":chat,"text":text,"disable_notification":"true" if disable_notification else "false"})
    mark_direct_delivery("text")
    return {"ok":True,"message_id":result.get("message_id"),"chat_id":str(result.get("chat",{}).get("id",chat))}

@mcp.tool()
def send_file(path:str,caption:str="",disable_notification:bool=False):
    _,chat=tg_need()
    p=Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    mime,_=mimetypes.guess_type(str(p))
    mime=mime or "application/octet-stream"
    endpoint,field=("sendDocument","document")
    if mime.startswith("image/"):
        endpoint,field=("sendPhoto","photo")
    elif mime.startswith("video/"):
        endpoint,field=("sendVideo","video")
    elif mime.startswith("audio/"):
        endpoint,field=("sendAudio","audio")
    with p.open("rb") as fh:
        result=tg(endpoint,{"chat_id":chat,"caption":caption or "","disable_notification":"true" if disable_notification else "false"},files={field:(p.name,fh,mime)})
    mark_direct_delivery("file")
    return {"ok":True,"message_id":result.get("message_id"),"chat_id":str(result.get("chat",{}).get("id",chat)),"sent_as":endpoint,"path":str(p)}

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]==WATCH:
        raise SystemExit(watch())
    mcp.run(transport="stdio")
