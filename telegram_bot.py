#!/usr/bin/env python3
"""Isolated Telegram control plane: lightweight JSON/text state + GitHub REST dispatch."""
import base64, json, os, re, time
from urllib.parse import quote
import requests

TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
CHAT_ID=str(os.environ.get("TELEGRAM_CHAT_ID","")).strip()
REPO=os.environ.get("GITHUB_REPOSITORY","shayanroyxyz/gaming-short-yt").strip()
GH_TOKEN=os.environ.get("GH_PAT","").strip() or os.environ.get("GITHUB_TOKEN","").strip()
API="https://api.github.com"
HEADERS={"Authorization":f"Bearer {GH_TOKEN}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
KEYBOARD={"keyboard":[
 [{"text":"🚀 Make Short Now"},{"text":"+ Add Video Link"}],
 [{"text":"🎯 Focus: AUTO"},{"text":"✏️ Custom Focus"}],
 [{"text":"📊 Cloud & YT Status"},{"text":"🩺 Self-Repair Now"}],
 [{"text":"🗑️ Delete Last"},{"text":"❌ Cancel"}]],
 "resize_keyboard":True,"one_time_keyboard":False,"is_persistent":False}

def tg(method,payload=None,timeout=25):
 r=requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}",data=payload or {},timeout=timeout)
 try: data=r.json()
 except ValueError: data={}
 if r.status_code==409 or data.get("error_code")==409: return {"ok":False,"error_code":409}
 return data

def send(chat,msg):
 if chat: tg("sendMessage",{"chat_id":chat,"text":str(msg)[:3900],"reply_markup":json.dumps(KEYBOARD,ensure_ascii=False)})

def gh(method,path,payload=None):
 r=requests.request(method,f"{API}/repos/{REPO}/{path.lstrip('/')}",headers=HEADERS,json=payload,timeout=25)
 if not r.ok: raise RuntimeError(f"GitHub REST {method} failed: HTTP {r.status_code}")
 return r.json() if r.content else {}

def read_file(path,default=""):
 try:
  item=gh("GET",f"contents/{quote(path)}?ref=main")
  return base64.b64decode(item.get("content","")).decode("utf-8")
 except Exception: return default

def read_json(path,default):
 try:
  value=json.loads(read_file(path,""))
  return value if isinstance(value,dict) else dict(default)
 except (ValueError,TypeError): return dict(default)

def save_files(updates,message):
 for attempt in range(3):
  ref=gh("GET","git/ref/heads/main"); parent=ref["object"]["sha"]
  commit=gh("GET",f"git/commits/{parent}")
  tree_rows=[]
  for path,content in updates.items():
   tree_rows.append({"path":path,"mode":"100644","type":"blob","content":content})
  tree=gh("POST","git/trees",{"base_tree":commit["tree"]["sha"],"tree":tree_rows})
  new=gh("POST","git/commits",{"message":message,"tree":tree["sha"],"parents":[parent]})
  try:
   gh("PATCH","git/refs/heads/main",{"sha":new["sha"],"force":False})
   return new["sha"]
  except RuntimeError:
   if attempt==2: raise
   time.sleep(attempt+1)
 raise RuntimeError("Could not persist bot state after three fast-forward attempts.")

def dispatch(workflow):
 r=requests.post(f"{API}/repos/{REPO}/actions/workflows/{workflow}/dispatches",
  headers=HEADERS,json={"ref":"main"},timeout=20)
 return r.status_code==204,f"HTTP {r.status_code}"

def filename(value):
 value=re.sub(r"[^A-Za-z0-9 _\-\[\].]","_",str(value or "").strip())
 value=re.sub(r"\s+","_",value).strip("._ ")[:100] or "Gaming_Clip"
 return value if value.lower().endswith((".mp4",".mkv",".webm")) else value+".mp4"

def youtube_url(text):
 m=re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s<>]+",text,re.I)
 return m.group(0).rstrip(".,;!?)") if m else ""

if not TOKEN or not CHAT_ID or not GH_TOKEN:
 print("Telegram poller skipped: bot token, owner chat ID or GitHub token missing.")
 raise SystemExit(0)

cfg=read_json("config.json",{"focus":"auto","last_video_id":"","pending_url":""})
hist=read_json("history.json",{})
state=read_json("bot_state.json",{"offset":0,"pending_action":"","pending_url":"","pending_since":0})
try: offset=max(0,int(state.get("offset",0)))
except (ValueError,TypeError): offset=0
links=[x.strip() for x in read_file("links.txt","").splitlines() if x.strip()]
state.setdefault("pending_action",""); state.setdefault("pending_url",""); state.setdefault("pending_since",0)
dirty=False; deadline=time.time()+210

def queue(source,name):
 line=f"{source} | {filename(name)}"
 if line not in links: links.append(line)

def persist():
 state["offset"]=offset
 state["updated_at"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
 save_files({"config.json":json.dumps(cfg,ensure_ascii=False,indent=2)+"\n",
  "bot_state.json":json.dumps(state,ensure_ascii=False,indent=2)+"\n",
  "links.txt":("\n".join(links)+"\n") if links else ""},
  "Telegram owner control state")

def persist_now():
 global dirty
 persist()
 dirty=False

while time.time()<deadline:
 try:
  result=tg("getUpdates",{"offset":offset,"timeout":20},timeout=25)
  if result.get("error_code")==409: break
  if not result.get("ok"): time.sleep(2); continue
 except requests.RequestException:
  time.sleep(2); continue
 updates=result.get("result",[])
 if not updates: continue
 for item in updates:
  offset=int(item.get("update_id",offset))+1
  dirty=True
  msg=item.get("message") or {}
  chat=str((msg.get("chat") or {}).get("id",""))
  if chat!=CHAT_ID: dirty=True; continue
  text=(msg.get("text") or msg.get("caption") or "").strip()
  command=text.split()[0].lower() if text.startswith("/") else ""
  media=msg.get("video") or msg.get("document") or msg.get("animation") or msg.get("video_note")
  if text=="❌ Cancel" or command=="/cancel":
   state.update({"pending_action":"","pending_url":"","pending_since":0}); cfg["pending_url"]=""
   persist_now(); send(chat,"Cancelled. Ready."); continue
  if media:
   url=youtube_url(text); size=int(media.get("file_size") or 0)
   if url:
    name=(msg.get("document") or {}).get("file_name") or f"Gameplay_{msg.get('message_id',int(time.time()))}.mp4"
    queue(url,name)
   elif 0<size<=1_950_000_000 and msg.get("message_id"):
    name=(msg.get("document") or {}).get("file_name") or f"[Telegram]_Clip_{msg['message_id']}.mp4"
    queue(f"tgmsg:{chat}:{msg['message_id']}",name)
   else:
    send(chat,"Not queued: file size is missing or exceeds the supported Telegram transfer limit."); dirty=True; continue
   persist_now(); ok,detail=dispatch("load_links.yml")
   send(chat,f"Queued. Loader dispatch: {detail}" if ok else f"Queued, but loader dispatch failed: {detail}")
   dirty=True; continue
  if not text: dirty=True; continue
  pending=state.get("pending_action","")
  if pending=="custom_focus" and not command:
   cfg["focus"]=text[:80].strip(); state.update({"pending_action":"","pending_since":0})
   persist_now(); send(chat,f"Focus saved: {cfg['focus']}.")
  elif pending=="link_name" and not command:
   queue(state.get("pending_url",""),text)
   state.update({"pending_action":"","pending_url":"","pending_since":0}); cfg["pending_url"]=""
   ok,detail=dispatch("load_links.yml")
   send(chat,f"Link queued. Loader dispatch: {detail}" if ok else f"Link queued; dispatch failed: {detail}")
  elif pending=="add_link" and not command:
   url=youtube_url(text)
   if not url: send(chat,"Please send a YouTube video URL, or tap Cancel.")
   else:
    label=text.replace(url,"").strip()
    if label:
     queue(url,label); state.update({"pending_action":"","pending_since":0})
     ok,detail=dispatch("load_links.yml")
     send(chat,f"Link queued. Loader dispatch: {detail}" if ok else f"Link queued; dispatch failed: {detail}")
    else:
     state.update({"pending_action":"link_name","pending_url":url,"pending_since":time.time()})
     cfg["pending_url"]=url; persist_now(); send(chat,"Link received. Send a short file name for this clip.")
  elif command in ("/start","/menu"): send(chat,"Owner control panel ready.")
  elif text=="🚀 Make Short Now" or command=="/make":
   persist_now(); ok,detail=dispatch("auto_upload.yml")
   send(chat,f"GitHub accepted the render request ({detail}); upload is not confirmed until the run finishes." if ok else f"Render dispatch failed: {detail}")
  elif text=="+ Add Video Link":
   state.update({"pending_action":"add_link","pending_since":time.time()})
   persist_now(); send(chat,"Send a YouTube video link. I will ask for a file name if needed.")
  elif text=="🎯 Focus: AUTO" or command=="/focus_auto":
   cfg["focus"]="auto"; persist_now(); send(chat,"Focus reset to AUTO.")
  elif text=="✏️ Custom Focus" or command=="/focus":
   arg=text.partition(" ")[2].strip() if command=="/focus" else ""
   if arg: cfg["focus"]=arg[:80]; persist_now(); send(chat,f"Focus saved: {cfg['focus']}.")
   else:
    state.update({"pending_action":"custom_focus","pending_since":time.time()})
    persist_now(); send(chat,"Type any game or topic name, e.g. GTA 6, GTA 5, RDR2, Physics, or Easter Eggs.")
  elif text=="📊 Cloud & YT Status" or command=="/status":
   entries=hist.get("recent_creative_entries",[])
   entries=[x for x in entries if isinstance(x,dict)] if isinstance(entries,list) else []
   latest=next((x for x in reversed(entries) if x.get("video_id")),{})
   uploads=hist.get("uploaded_source_windows",[]); cuts=hist.get("used_windows",[])
   send(chat,"Cloud & YouTube status (saved repository snapshot)\n"
    f"• Focus: {cfg.get('focus','auto')}\n• Queued links: {len(links)}\n"
    f"• Recorded uploads: {len(uploads) if isinstance(uploads,list) else 0}\n"
    f"• Recorded cuts: {len(cuts) if isinstance(cuts,list) else 0}\n"
    f"• Latest recorded Short: {latest.get('video_id','not recorded')}\n"
    "• Live cloud quota / Studio counters are not queried by the isolated bot.")
  elif text=="🩺 Self-Repair Now" or command=="/repair":
   persist_now(); ok,detail=dispatch("self_repair.yml")
   send(chat,f"Self-repair accepted ({detail}); check its GitHub Actions run for results." if ok else f"Self-repair dispatch failed: {detail}")
  elif text=="🗑️ Delete Last" or command=="/delete_last":
   persist_now(); ok,detail=dispatch("delete_last.yml")
   send(chat,f"Delete-last workflow accepted ({detail}); verify its run before assuming deletion." if ok else f"Delete-last dispatch failed: {detail}")
  elif command=="/help":
   send(chat,"Use the menu to render, queue a link, set focus, view saved status, run repair, delete the last recorded Short, or cancel.")
  else: send(chat,"I did not recognize that command. Use the menu or /help.")

if dirty:
 try: persist()
 except Exception as exc: print(f"Could not persist lightweight Telegram state: {type(exc).__name__}: {exc}")
print("Telegram poller finished.")
