import os, re, time, json, base64, threading, requests, xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"]).strip()
GH_PAT = os.environ["GH_PAT"].strip()
REPO = "shayanroyxyz/gta-shorts-agent"
GH_HEADERS = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"}

MAIN_KB = {
    "keyboard": [
        [{"text": "🚀 Make Short Now"}, {"text": "➕ Add Video Link"}],
        [{"text": "🔥 Live Hype"}, {"text": "📊 Cloud Status"}],
        [{"text": "📈 YT Stats"}, {"text": "🗑️ Delete Last"}],
        [{"text": "🎯 Focus: GTA 6"}, {"text": "🎯 Focus: Auto"}],
        [{"text": "❓ Help"}, {"text": "❌ Cancel"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

TAG_KB = {
    "keyboard": [
        [{"text": "🎮 [GTA6]"}, {"text": "🚗 [GTA5]"}],
        [{"text": "🗽 [GTA4]"}, {"text": "⛏️ [Minecraft]"}],
        [{"text": "🧱 [Roblox]"}, {"text": "🔫 [Valorant]"}],
        [{"text": "❌ Cancel"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

def send(cid, text, kb=MAIN_KB):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": text, "reply_markup": json.dumps(kb)}, timeout=15)

def trigger_wf(wf):
    requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches", headers=GH_HEADERS, json={"ref": "main"}, timeout=15)

def gh_get(path):
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=GH_HEADERS, timeout=15).json()
    return (base64.b64decode(r["content"]).decode() if r.get("content") else ""), r.get("sha")

def gh_put(path, txt, sha, msg):
    p = {"message": msg, "content": base64.b64encode(txt.encode()).decode()}
    if sha: p["sha"] = sha
    requests.put(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=GH_HEADERS, json=p, timeout=15)

def queue_link(cid, url, raw_name):
    safe = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", raw_name.strip())
    if not safe.endswith(".mp4"): safe += ".mp4"
    cur, sha = gh_get("links.txt")
    gh_put("links.txt", cur + f"{url} | {safe}\n", sha, f"Queue {safe}")
    trigger_wf("load_links.yml")
    send(cid, f"✅ Queued & Loader Started!\nFile: {safe}\nDownloading 720p straight to MEGA/pCloud now!", MAIN_KB)

def get_hype():
    out = []
    for q in ["GTA+6", "GTA+5", "Minecraft", "Roblox", "Valorant"]:
        try:
            r = requests.get(f"https://news.google.com/rss/search?q={q}+gaming+when:2d&hl=en-US&gl=US&ceid=US:en", timeout=8)
            for item in ET.fromstring(r.text).findall(".//item")[:2]: out.append(item.find("title").text.split(" - ")[0])
        except Exception: pass
    return "\n• ".join(out[:8]) if out else "GTA 6 Free Roam, GTA 4 Physics, Minecraft Secrets"

port = int(os.environ.get("PORT", 10000))
threading.Thread(target=lambda: HTTPServer(("0.0.0.0", port), type("H", (BaseHTTPRequestHandler,), {"do_GET": lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"OK"))})).serve_forever(), daemon=True).start()

requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=10)
offset, pending = 0, ""

while True:
    try:
        updates = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 25}, timeout=30).json().get("result", [])
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            cid = str((msg.get("chat") or {}).get("id", ""))
            if cid != CHAT_ID: continue
            text = (msg.get("text") or "").strip()
            if not text: continue

            if text == "❌ Cancel":
                pending = ""
                send(cid, "❌ Cancelled. Ready!", MAIN_KB)
            elif "youtu.be/" in text or "youtube.com/" in text:
                parts = text.split(None, 1)
                if len(parts) > 1 and len(parts[1].strip()) > 2: queue_link(cid, parts[0], parts[1]); pending = ""
                else: pending = parts[0]; send(cid, "🎬 Link received! Type a file name OR tap a game tag:", TAG_KB)
            elif pending:
                tmap = {"🎮 [GTA6]": "GTA6", "🚗 [GTA5]": "GTA5", "🗽 [GTA4]": "GTA4", "⛏️ [Minecraft]": "Minecraft", "🧱 [Roblox]": "Roblox", "🔫 [Valorant]": "Valorant"}
                queue_link(cid, pending, f"[{tmap[text]}]_Gameplay_{int(time.time()) % 10000}.mp4" if text in tmap else text)
                pending = ""
            elif text == "➕ Add Video Link": send(cid, "📎 Paste any YouTube gameplay link right now!", MAIN_KB)
            elif text in ["🚀 Make Short Now", "/make"]: trigger_wf("auto_upload.yml"); send(cid, "🚀 Triggered! Publishing to YT, IG Reels & Telegram in ~60s.", MAIN_KB)
            elif text in ["🎯 Focus: GTA 6", "🎯 Focus: Auto"]:
                val = "gta6" if "GTA 6" in text else "auto"
                cur, sha = gh_get("config.json")
                cfg = json.loads(cur) if cur else {"focus": "auto", "last_video_id": ""}
                cfg["focus"] = val
                gh_put("config.json", json.dumps(cfg, indent=2), sha, f"Focus {val}")
                send(cid, f"🎯 Focus switched to: {val.upper()}", MAIN_KB)
            elif text in ["🔥 Live Hype", "/hype"]: send(cid, "🔥 Live US Gaming Hype:\n• " + get_hype(), MAIN_KB)
            elif text in ["📊 Cloud Status", "/status"]:
                h, _ = gh_get("history.json"); c, _ = gh_get("config.json")
                send(cid, f"📊 Pipeline Status:\n• Unique Shorts Made: {len(json.loads(h).get('used_windows', [])) if h else 0}\n• Focus: {(json.loads(c).get('focus', 'auto') if c else 'auto').upper()}\n• Schedule: 6x Daily (US Prime Time)", MAIN_KB)
            elif text in ["📈 YT Stats", "/stats"]:
                c, _ = gh_get("config.json"); vid = json.loads(c).get("last_video_id", "") if c else ""
                send(cid, f"📈 Latest Short: https://youtube.com/shorts/{vid}" if vid else "📈 No Short yet — tap 🚀 Make Short Now!", MAIN_KB)
            elif text in ["🗑️ Delete Last", "/delete_last"]:
                c, sha = gh_get("config.json")
                cfg = json.loads(c) if c else {}
                vid = cfg.get("last_video_id", "")
                if vid:
                    cfg["last_video_id"] = ""
                    gh_put("config.json", json.dumps(cfg, indent=2), sha, "Clear last_video_id")
                    send(cid, f"🗑️ Cleared Short ID {vid} from queue (delete video in YT Studio if already public).", MAIN_KB)
                else:
                    send(cid, "No recent Short ID stored.", MAIN_KB)
            else: send(cid, "🎮 24/7 Instant Owner Control Panel Active:", MAIN_KB)
    except Exception: time.sleep(3)
