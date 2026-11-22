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

def send(cid, text, kb=MAIN_KB):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": text, "reply_markup": json.dumps(kb)}, timeout=15)

def trigger_wf(wf):
    try:
        response = requests.post(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{wf}/dispatches",
            headers=GH_HEADERS, json={"ref": "main"}, timeout=20
        )
        return response.status_code == 204
    except requests.RequestException as exc:
        print("Workflow dispatch failed:", repr(exc))
        return False

def gh_get(path):
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=GH_HEADERS, timeout=15)
    if r.status_code != 200: return "", None
    d = r.json()
    return (base64.b64decode(d["content"]).decode() if d.get("content") else ""), d.get("sha")

def gh_append_line(path, new_line, msg):
    for _ in range(8):
        cur, sha = gh_get(path)
        updated = (cur.rstrip("\n") + "\n" if cur.strip() else "") + new_line.strip() + "\n"
        p = {"message": msg, "content": base64.b64encode(updated.encode()).decode()}
        if sha: p["sha"] = sha
        res = requests.put(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=GH_HEADERS, json=p, timeout=15)
        if res.status_code in (200, 201): return True
        time.sleep(0.8)
    return False

def gh_put(path, txt, msg):
    for _ in range(6):
        _, sha = gh_get(path)
        p = {"message": msg, "content": base64.b64encode(txt.encode()).decode()}
        if sha: p["sha"] = sha
        res = requests.put(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=GH_HEADERS, json=p, timeout=15)
        if res.status_code in (200, 201): return True
        time.sleep(0.8)
    return False

def load_bot_state():
    raw, _ = gh_get("bot_state.json")
    try:
        state = json.loads(raw) if raw else {}
        return int(state.get("offset", 0)), state.get("pending", "")
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0, ""

def save_bot_state(offset, pending):
    payload = json.dumps({"offset": offset, "pending": pending}, indent=2)
    if not gh_put("bot_state.json", payload, "Persist Telegram bot polling state"):
        print("WARNING: could not persist Telegram polling state")

def safe_video_filename(raw_name):
    stem, ext = os.path.splitext(str(raw_name).strip())
    safe_stem = re.sub(r"[^a-zA-Z0-9_\[\]-]+", "_", stem).strip("_") or "clip"
    safe_ext = ext.lower() if ext.lower() in (".mp4", ".mkv", ".webm") else ".mp4"
    return safe_stem + safe_ext

def queue_item(cid, source, raw_name):
    safe = safe_video_filename(raw_name)
    ok = gh_append_line("links.txt", f"{source} | {safe}", f"Queue {safe}")
    if ok:
        send(cid, f"✅ Queued ({safe})!\n⏳ Waiting for the next GitHub workflow run. Use 🚀 Make Short Now or /make to start the pipeline now.", FOLDED_KB)
    else:
        send(cid, f"⚠️ GitHub busy — tap the tag again for {safe}.", TAG_KB)

def detect_tag(text):
    t = text.lower()
    if "gta 6" in t or "gta6" in t: return "GTA6"
    if "gta 4" in t or "gta4" in t: return "GTA4"
    if "gta" in t: return "GTA5"
    if "minecraft" in t: return "Minecraft"
    if "roblox" in t: return "Roblox"
    if "valorant" in t: return "Valorant"
    return None

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

requests.post(f"https://api.telegram.org/bot{TOKEN}/setMyCommands", json={"commands": [
    {"command": "menu", "description": "Open Control Buttons"},
    {"command": "make", "description": "Make & Publish Short Now"},
    {"command": "hype", "description": "Live Viral Gaming Trends"},
    {"command": "status", "description": "Cloud & Pipeline Status"},
    {"command": "stats", "description": "Latest YouTube Short"},
    {"command": "cancel", "description": "Fold / Cancel"}
]}, timeout=10)

requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", params={"drop_pending_updates": False}, timeout=10)
offset, pending = load_bot_state()
seen = set()

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
            mid = msg.get("message_id")
            if cid != CHAT_ID: continue

            media = msg.get("video") or msg.get("document")
            if media and media.get("file_id"):
                sz = round(media.get("file_size", 0) / 1048576, 1)
                cap = (msg.get("caption") or "").strip()
                src = f"tgmsg:{cid}:{mid}"
                auto_tag = detect_tag(cap)
                if auto_tag:
                    queue_item(cid, src, f"[{auto_tag}]_Clip_{mid}.mp4")
                    pending = ""
                else:
                    pending = src
                    send(cid, f"🎥 Video received ({sz} MB)!\nTap a game tag below (or type a custom name):", TAG_KB)
                save_bot_state(offset, pending)
                continue

            text = (msg.get("text") or "").strip()
            if not text:
                save_bot_state(offset, pending)
                continue

            if text in ["❌ Cancel", "/cancel"]:
                pending = ""
                send(cid, "✅ Folded. Tap ≡ Menu or /menu anytime.", FOLDED_KB)
            elif text in ["/start", "/menu"]:
                pending = ""
                send(cid, "🎮 Owner Control Panel (auto-folds after tap):", MAIN_KB)
            elif "youtu.be/" in text or "youtube.com/" in text:
                parts = text.split(None, 1)
                if len(parts) > 1 and len(parts[1].strip()) > 2: queue_item(cid, parts[0], parts[1]); pending = ""
                else: pending = parts[0]; send(cid, "🎬 Link received! Type a file name OR tap a game tag:", TAG_KB)
            elif pending:
                tmap = {"🎮 [GTA6]": "GTA6", "🚗 [GTA5]": "GTA5", "🗽 [GTA4]": "GTA4", "⛏️ [Minecraft]": "Minecraft", "🧱 [Roblox]": "Roblox", "🔫 [Valorant]": "Valorant"}
                queue_item(cid, pending, f"[{tmap[text]}]_Clip_{int(time.time()) % 10000}.mp4" if text in tmap else text)
                pending = ""
            elif text == "➕ Add Video Link": send(cid, "📎 Forward a video from @gozillabot_downloaderbot_bot, upload from Snaptube, or paste a YouTube link!", FOLDED_KB)
            elif text in ["🚀 Make Short Now", "/make"]:
                if trigger_wf("auto_upload.yml"):
                    send(cid, "🚀 Workflow accepted by GitHub. I will report the actual publish result when the run finishes.", FOLDED_KB)
                else:
                    send(cid, "⚠️ GitHub did not accept the workflow request. Check the GH_PAT Actions permission and GitHub Actions status.", FOLDED_KB)
            elif text in ["🎯 Focus: GTA 6", "🎯 Focus: Auto"]:
                val = "gta6" if "GTA 6" in text else "auto"
                cur, _ = gh_get("config.json")
                cfg = json.loads(cur) if cur else {"focus": "auto", "last_video_id": ""}
                cfg["focus"] = val
                gh_put("config.json", json.dumps(cfg, indent=2), f"Focus {val}")
                send(cid, f"🎯 Focus switched to: {val.upper()}", FOLDED_KB)
            elif text in ["🔥 Live Hype", "/hype"]: send(cid, "🔥 Live Viral Gaming Search Trends:\n• " + get_viral_gaming_hype(), FOLDED_KB)
            elif text in ["📊 Cloud Status", "/status"]:
                h, _ = gh_get("history.json"); c, _ = gh_get("config.json"); q, _ = gh_get("links.txt")
                queued = len([line for line in (q or "").splitlines() if "|" in line])
                send(cid, f"📊 Pipeline Status:\n• Unique Shorts Made: {len(json.loads(h).get('used_windows', [])) if h else 0}\n• Videos waiting in queue: {queued}\n• Focus: {(json.loads(c).get('focus', 'auto') if c else 'auto').upper()}\n• Auto schedule: unchanged (6x daily)", FOLDED_KB)
            elif text in ["📈 YT Stats", "/stats"]:
                c, _ = gh_get("config.json"); vid = json.loads(c).get("last_video_id", "") if c else ""
                send(cid, f"📈 Latest Short: https://youtube.com/shorts/{vid}" if vid else "📈 No Short yet — tap /make!", FOLDED_KB)
            elif text in ["🗑️ Delete Last", "/delete_last"]:
                c, _ = gh_get("config.json")
                cfg = json.loads(c) if c else {}
                vid = cfg.get("last_video_id", "")
                if vid:
                    cfg["last_video_id"] = ""
                    gh_put("config.json", json.dumps(cfg, indent=2), "Clear last_video_id")
                    send(cid, f"🗑️ Cleared Short ID {vid} from queue.", FOLDED_KB)
                else:
                    send(cid, "No recent Short ID stored.", FOLDED_KB)
            else:
                send(cid, "🎮 Control Panel (tap a button or ❌ Cancel to fold):", MAIN_KB)
            save_bot_state(offset, pending)
    except Exception as e:
        print("Telegram polling error:", repr(e))
        time.sleep(3)
