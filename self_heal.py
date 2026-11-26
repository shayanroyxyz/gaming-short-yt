#!/usr/bin/env python3
"""Repair JSON/text state, stale Telegram prompts, queue hygiene and AI-provider health."""
import json, os, re, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parent
DEFAULTS={
 "config.json":{"focus":"auto","last_video_id":"","pending_url":""},
 "history.json":{"used_windows":[],"used_topics":[],"recent_scripts":[],"recent_creative_entries":[],"used_sources":[],"uploaded_source_windows":[],"used_source_windows":[],"published_source_files":[]},
 "bot_state.json":{"offset":0,"pending":"","pending_action":"","pending_url":"","pending_since":0},
}
def log(msg): print("[self-heal] "+msg,flush=True)
def git_sync_guard():
 if not (ROOT/".git").exists(): log("Git sync skipped: no repository metadata."); return
 fetch=subprocess.run(["git","fetch","origin","main"],cwd=ROOT,capture_output=True,text=True,timeout=90)
 if fetch.returncode: raise RuntimeError("git fetch origin main failed: "+(fetch.stderr or fetch.stdout)[-400:])
 pull=subprocess.run(["git","pull","--rebase","--autostash","origin","main"],cwd=ROOT,capture_output=True,text=True,timeout=120)
 if pull.returncode:
  subprocess.run(["git","rebase","--abort"],cwd=ROOT,capture_output=True,text=True,timeout=30)
  raise RuntimeError("Git rebase conflict safely aborted; no force overwrite was attempted. "+(pull.stderr or pull.stdout)[-600:])
 log("git pull --rebase --autostash origin main passed.")
def backup(path):
 if path.exists():
  stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  target=path.with_name(path.name+".corrupt-"+stamp+".bak")
  shutil.copy2(path,target); log("Backed up invalid "+path.name+" in this workflow runner.")
def repair_json(name,defaults):
 path=ROOT/name; bad=not path.exists() or path.stat().st_size==0; data=None
 if not bad:
  try:
   data=json.loads(path.read_text(encoding="utf-8"))
   if not isinstance(data,dict): bad=True
  except (OSError,UnicodeError,json.JSONDecodeError): bad=True
 if bad:
  backup(path); data=dict(defaults); log("Rebuilt "+name+" from schema defaults.")
 else:
  for key,default in defaults.items():
   if key not in data or not isinstance(data[key],type(default)):
    data[key]=default; log("Repaired invalid "+name+"."+key+".")
 if name=="config.json":
  err=str(data.get("analytics_last_error",""))
  if re.search(r"(?:[?&](?:key|token|access_token)=|AIza[0-9A-Za-z_-]{20,})",err,re.I):
   data.pop("analytics_last_error",None); data.pop("analytics_last_attempt_at",None)
   log("Removed credential-bearing analytics error text from config.json.")
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 return data
def repair_links():
 path=ROOT/"links.txt"
 if not path.exists(): path.write_text("",encoding="utf-8"); return
 before=path.read_text(encoding="utf-8",errors="replace")
 seen=set(); clean=[]
 for raw in before.splitlines():
  line=raw.strip()
  if not line or "|" not in line: continue
  source,name=(x.strip() for x in line.split("|",1))
  valid=source.startswith(("http://","https://")) or re.fullmatch(r"tgmsg:-?\d+:\d+",source)
  name=re.sub(r"[^A-Za-z0-9 _\-\[\].]","_",name).strip(" ._")
  row=f"{source} | {name}"
  if valid and name and len(name)<=120 and row not in seen: seen.add(row); clean.append(row)
 after=("\n".join(clean)+"\n") if clean else ""
 if before!=after: path.write_text(after,encoding="utf-8"); log(f"Cleaned links.txt; {len(clean)} unique valid entries remain.")
def clear_stale_prompt(state):
 try: age=time.time()-float(state.get("pending_since",0))
 except (TypeError,ValueError): age=10**9
 if (state.get("pending_action") or state.get("pending")) and age>900:
  state.update({"pending":"","pending_action":"","pending_url":"","pending_since":0})
  log("Cleared Telegram prompt older than 15 minutes.")
 return state
def check(name,url,key,headers=None,params=None):
 if not key: return False,"missing key"
 try:
  r=requests.get(url,headers=headers or {},params=params or {},timeout=15)
  return (True,"healthy") if r.status_code==200 else (False,f"HTTP {r.status_code}")
 except requests.RequestException as exc: return False,type(exc).__name__
def provider_health():
 gem=os.environ.get("GEMINI_API_KEY","").strip()
 groq=os.environ.get("GROQ_API_KEY","").strip()
 router=os.environ.get("OPENROUTER_API_KEY","").strip()
 results={
  "gemini":check("gemini","https://generativelanguage.googleapis.com/v1beta/models",gem,params={"key":gem,"pageSize":1}),
  "groq":check("groq","https://api.groq.com/openai/v1/models",groq,headers={"Authorization":"Bearer "+groq}),
  "openrouter":check("openrouter","https://openrouter.ai/api/v1/models",router,headers={"Authorization":"Bearer "+router}),
  "github_models":(False,"retired on 2026-07-30"),
 }
 disabled=[name for name,(ok,_) in results.items() if not ok]
 for name,(ok,reason) in results.items(): log(f"{name}: {'healthy' if ok else 'disabled for this run'} ({reason}).")
 env=os.environ.get("GITHUB_ENV")
 if env:
  with open(env,"a",encoding="utf-8") as out: out.write("AI_DISABLED_PROVIDERS="+",".join(disabled)+"\n")
 return results
def main():
 git_sync_guard()
 repair_json("config.json",DEFAULTS["config.json"])
 repair_json("history.json",DEFAULTS["history.json"])
 state=clear_stale_prompt(repair_json("bot_state.json",DEFAULTS["bot_state.json"]))
 (ROOT/"bot_state.json").write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 repair_links()
 results=provider_health()
 healthy=[k for k,(ok,_) in results.items() if ok]
 log("Repair complete. Healthy providers: "+(", ".join(healthy) if healthy else "none; generation will fail closed, not invent claims")+".")
 return 0
if __name__=="__main__": raise SystemExit(main())
