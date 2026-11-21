import os, re, time, json, base64, threading, requests
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
    "one_time_keyboard": True
}

TAG_KB = {
    "keyboard": [
        [{"text": "🎮 [GTA6]"}, {"text": "🚗 [GTA5]"}],
        [{"text": "🗽 [GTA4]"}, {"text": "⛏️ [Minecraft]"}],
        [{"text": "🧱 [Roblox]"}, {"text": "🔫 [Valorant]"}],
        [{"text": "❌ Cancel"}]
    ],
    "resize_keyboard": True,
    "one_time_keyboard": True
}

FOLDED_KB = {"remove_keyboard": True}

def send(cid, text, kb=FOLDED_KB):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": text, "reply_markup": json.dumps(kb)}, timeout=15)

def trigger_wf(wf):
    requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches", headers=GH_HEADERS, json={"ref": "main"}, timeout=15)

def gh_get(path):
    response = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=GH_HEADERS, timeout=20)
    if response.status_code == 404:
        return "", None
    response.raise_for_status()
    payload = response.json()
    return (base64.b64decode(payload["content"]).decode() if payload.get("content") else ""), payload.get("sha")

def gh_put(path, txt, sha, msg):
    payload = {"message": msg, "content": base64.b64encode(txt.encode()).decode()}
    if sha:
        payload["sha"] = sha
    response = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{path}",
        headers=GH_HEADERS, json=payload, timeout=20
    )
    return response

def safe_queue_filename(raw_name):
    name = re.sub(r"[^a-zA-Z0-9_.()\\[\\]-]", "_", os.path.basename(raw_name.strip()))
    name = name.strip("._") or f"Gameplay_{int(time.time())}.mp4"
    if not os.path.splitext(name)[1]:
        name += ".mp4"
    return name[:180]

def queue_item(cid, source, raw_name):
    safe = safe_queue_filename(raw_name)
    for attempt in range(6):
        cur, sha = gh_get("links.txt")
        line = f"{source} | {safe}"
        if any(existing.strip().split("|", 1)[0].strip() == source for existing in cur.splitlines()):
            send(cid, f"ℹ️ This Telegram message is already queued.\\n📁 {safe}", FOLDED_KB)
            return
        updated = cur + ("" if not cur or cur.endswith("\\n") else "\\n") + line + "\\n"
        response = gh_put("links.txt", updated, sha, f"Queue {safe}")
        if response.status_code in (200, 201):
            trigger_wf("load_links.yml")
            send(cid, f"✅ Queued for cloud transfer!\\n📁 {safe}\\n☁️ MTProto download → one cloud with failover.", FOLDED_KB)
            return
        if response.status_code not in (409, 422):
            response.raise_for_status()
        time.sleep(min(2 + attempt, 7))
    raise RuntimeError("Could not append to links.txt after 6 GitHub SHA-conflict retries")

def detect_game_tag(caption):
    for tag in ("GTA6", "GTA5", "GTA4", "Minecraft", "Roblox", "Valorant"):
        if re.search(r"\\[" + re.escape(tag) + r"\\]", caption or "", re.IGNORECASE):
            return tag
    return ""

def tagged_filename(tag, raw_name):
    base = safe_queue_filename(raw_name)
    if tag and not re.search(r"\\[" + re.escape(tag) + r"\\]", base, re.IGNORECASE):
        base = f"[{tag}]_{base}"
    return base

def get_viral_gaming_hype():
    topics = []
    for q in ["GTA 6 secrets physics", "GTA 5 insane mods myths", "Minecraft 1000 IQ tricks", "Roblox viral obby secrets", "Valorant radiant clutches"]:
        try:
            r = requests.get(f"https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={requests.utils.quote(q)}", timeout=6).json()
            for s in r[1][:2]: topics.append(s.title())
        except Exception: pass
    return "\n• ".join(topics[:8]) if topics else "GTA 6 Hidden Map Details\n• GTA 4 vs GTA 6 Ragdoll Physics\n• Minecraft Secret Redstone Traps"

port = int(os.environ.get("PORT", 10000))
threading.Thread(target=lambda: HTTPServer(("0.0.0.0", port), type("H", (BaseHTTPRequestHandler,), {"do_GET": lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"OK"))})).serve_forever(), daemon=True).start()

# Register native Menu button commands so menu starts folded by default
requests.post(f"https://api.telegram.org/bot{TOKEN}/setMyCommands", json={"commands": [
    {"command": "menu", "description": "Open Control Buttons"},
    {"command": "make", "description": "Make & Publish Short Now"},
    {"command": "hype", "description": "Live Viral Gaming Trends"},
    {"command": "status", "description": "Cloud & Pipeline Status"},
    {"command": "stats", "description": "Latest YouTube Short"},
    {"command": "cancel", "description": "Fold / Cancel"}
]}, timeout=10)

requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", params={"drop_pending_updates": True}, timeout=10)
offset, pending, seen = 0, "", set()

while True:
    try:
        resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 25}, timeout=30).json()
        if not resp.get("ok"):
            time.sleep(5)
            continue
        for u in resp.get("result", []):
            uid = u["update_id"]
            offset = uid + 1
            if uid in seen: continue
            seen.add(uid)
            if len(seen) > 200: seen = set(list(seen)[-100:])

            msg = u.get("message") or {}
            cid = str((msg.get("chat") or {}).get("id", ""))
            if cid != CHAT_ID: continue

            # 1. Handle Forwarded Video from Downloader Bot OR Direct Snaptube Video Upload
            media = msg.get("video") or msg.get("document")
            if media and (msg.get("video") or str(media.get("mime_type", "")).startswith("video/")):
                cap = (msg.get("caption") or "").strip()
                source = f"tgmsg:{cid}:{msg.get('message_id')}"
                raw_name = media.get("file_name") or (msg.get("video") and f"Gameplay_{msg.get('message_id')}.mp4") or f"Gameplay_{msg.get('message_id')}.mp4"
                detected_tag = detect_game_tag(cap)
                if detected_tag:
                    queue_item(cid, source, tagged_filename(detected_tag, raw_name))
                    pending = ""
                else:
                    pending = (source, raw_name)
                    size_mb = round(media.get("file_size", 0) / 1048576, 1)
                    send(cid, f"🎥 Video received ({size_mb} MB). Choose a game tag or type a filename:", TAG_KB)
                continue

            text = (msg.get("text") or "").strip()
            if not text: continue

            if text in ["❌ Cancel", "/cancel"]:
                pending = ""
                send(cid, "✅ Folded. Tap ≡ Menu or /menu anytime.", FOLDED_KB)
            elif text == "/menu":
                pending = ""
                send(cid, "🎮 Owner Control Panel (auto-folds after tap):", MAIN_KB)
            elif text == "/start":
                pending = ""
                send(cid, "Welcome! Type /menu to open controls.", FOLDED_KB)
            elif "youtu.be/" in text or "youtube.com/" in text:
                parts = text.split(None, 1)
                if len(parts) > 1 and len(parts[1].strip()) > 2: queue_item(cid, parts[0], parts[1]); pending = ""
                else: pending = parts[0]; send(cid, "🎬 Link received! Type a file name OR tap a game tag:", TAG_KB)
            elif pending:
                tmap = {"🎮 [GTA6]": "GTA6", "🚗 [GTA5]": "GTA5", "🗽 [GTA4]": "GTA4", "⛏️ [Minecraft]": "Minecraft", "🧱 [Roblox]": "Roblox", "🔫 [Valorant]": "Valorant"}
                source, original_name = pending
                chosen_tag = tmap.get(text, "")
                final_name = tagged_filename(chosen_tag, original_name) if chosen_tag else text
                queue_item(cid, source, final_name)
                pending = ""
            elif text == "➕ Add Video Link": send(cid, "📎 Forward a video from @gozillabot_downloaderbot_bot, upload from Snaptube, or paste a YouTube link!", FOLDED_KB)
            elif text in ["🚀 Make Short Now", "/make"]: trigger_wf("auto_upload.yml"); send(cid, "🚀 Triggered! Publishing to YT, IG Reels & Telegram in ~60s.", FOLDED_KB)
            elif text in ["🎯 Focus: GTA 6", "🎯 Focus: Auto"]:
                val = "gta6" if "GTA 6" in text else "auto"
                cur, sha = gh_get("config.json")
                cfg = json.loads(cur) if cur else {"focus": "auto", "last_video_id": ""}
                cfg["focus"] = val
                gh_put("config.json", json.dumps(cfg, indent=2), sha, f"Focus {val}")
                send(cid, f"🎯 Focus switched to: {val.upper()}", FOLDED_KB)
            elif text in ["🔥 Live Hype", "/hype"]: send(cid, "🔥 Live Viral Gaming Search Trends:\n• " + get_viral_gaming_hype(), FOLDED_KB)
            elif text in ["📊 Cloud Status", "/status"]:
                h, _ = gh_get("history.json"); c, _ = gh_get("config.json")
                send(cid, f"📊 Pipeline Status:\n• Unique Shorts Made: {len(json.loads(h).get('used_windows', [])) if h else 0}\n• Focus: {(json.loads(c).get('focus', 'auto') if c else 'auto').upper()}\n• Schedule: 6x Daily (US Prime Time)", FOLDED_KB)
            elif text in ["📈 YT Stats", "/stats"]:
                c, _ = gh_get("config.json"); vid = json.loads(c).get("last_video_id", "") if c else ""
                send(cid, f"📈 Latest Short: https://youtube.com/shorts/{vid}" if vid else "📈 No Short yet — tap /make!", FOLDED_KB)
            elif text in ["🗑️ Delete Last", "/delete_last"]:
                c, sha = gh_get("config.json")
                cfg = json.loads(c) if c else {}
                vid = cfg.get("last_video_id", "")
                if vid:
                    cfg["last_video_id"] = ""
                    gh_put("config.json", json.dumps(cfg, indent=2), sha, "Clear last_video_id")
                    send(cid, f"🗑️ Cleared Short ID {vid} from queue.", FOLDED_KB)
                else:
                    send(cid, "No recent Short ID stored.", FOLDED_KB)
            else:
                send(cid, "🎮 Control Panel (tap a button or ❌ Cancel to fold):", MAIN_KB)
    except Exception: time.sleep(3)
