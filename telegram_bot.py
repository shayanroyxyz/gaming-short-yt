import os, re, json, time, subprocess, xml.etree.ElementTree as ET, requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
CHANNEL_ID = str(os.environ.get("TELEGRAM_CHANNEL_ID", "")).strip()
GH_PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "shayanroyxyz/gaming-short-yt")

MAIN_KEYBOARD = {
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

GAME_TAG_KEYBOARD = {
    "keyboard": [
        [{"text": "🎮 [GTA6]"}, {"text": "🚗 [GTA5]"}],
        [{"text": "🗽 [GTA4]"}, {"text": "⛏️ [Minecraft]"}],
        [{"text": "🧱 [Roblox]"}, {"text": "🔫 [Valorant]"}],
        [{"text": "❌ Cancel"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

def send_msg(target_chat, text, kb=MAIN_KEYBOARD):
    if TOKEN and target_chat:
        payload = {"chat_id": target_chat, "text": text}
        if kb and not str(target_chat).startswith("-100"):
            payload["reply_markup"] = json.dumps(kb)
        try:
            response = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload, timeout=15)
            if not response.ok:
                print(f"Telegram sendMessage failed: HTTP {response.status_code}: {response.text[:500]}", flush=True)
        except requests.RequestException as exc:
            print(f"Telegram sendMessage request failed: {type(exc).__name__}: {exc}", flush=True)

def trigger_workflow(wf_file):
    if not GH_PAT:
        return "not sent (GH_PAT is not configured)"
    try:
        response = requests.post(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{wf_file}/dispatches",
            headers={"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"},
            json={"ref": "main"},
            timeout=15
        )
        detail = (response.text or "").strip().replace("\\n", " ")[:240]
        if response.status_code == 204:
            return "HTTP 204 Accepted"
        return f"HTTP {response.status_code}: {detail or response.reason}"
    except requests.RequestException as exc:
        return f"request error: {type(exc).__name__}: {exc}"

def get_yt_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build("youtube", "v3", credentials=creds)

def get_live_hype():
    headlines = []
    for q in ["GTA+6", "GTA+5", "Minecraft", "Roblox", "Valorant"]:
        try:
            r = requests.get(f"https://news.google.com/rss/search?q={q}+gaming+when:2d&hl=en-US&gl=US&ceid=US:en", timeout=8)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item")[:2]:
                headlines.append(item.find("title").text.split(" - ")[0])
        except Exception:
            pass
    return "\n• ".join(headlines[:8]) if headlines else "GTA 6 Free Roam, GTA 4 vs GTA 6 Physics, Minecraft Impossible Tricks"

def queue_video_link(target_chat, url, raw_name):
    safe_name = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", raw_name.strip())
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    with open("links.txt", "a") as f:
        f.write(f"{url} | {safe_name}\n")
    subprocess.run(["git", "config", "user.name", "OwnerBot"], check=False)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "links.txt"], check=False)
    subprocess.run(["git", "commit", "-m", f"Queue {safe_name}"], check=False)
    if GH_PAT:
        subprocess.run(["git", "push", f"https://x-access-token:{GH_PAT}@github.com/{REPO}.git"], check=False)
    trigger_workflow("load_links.yml")
    source_note = "Downloading the YouTube source" if str(url).startswith(("http://", "https://")) else "Downloading the Telegram video through the MTProto loader"
    send_msg(target_chat, f"✅ Queued & Loader Started!\nFile: {safe_name}\n{source_note} to MEGA/pCloud now!", MAIN_KEYBOARD)

if not TOKEN or not CHAT_ID:
    exit(0)

try:
    webhook_resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", params={"drop_pending_updates": "false"}, timeout=10)
    webhook_data = webhook_resp.json()
    if not webhook_resp.ok or not webhook_data.get("ok"):
        print(f"Telegram deleteWebhook warning: HTTP {webhook_resp.status_code}: {webhook_data}", flush=True)
except (requests.RequestException, ValueError) as exc:
    print(f"Telegram deleteWebhook warning: {type(exc).__name__}: {exc}", flush=True)

# bot_state.json is the single canonical offset store. Recover safely from malformed state.
try:
    state = json.load(open("bot_state.json", encoding="utf-8")) if os.path.exists("bot_state.json") else {}
    raw_offset = state.get("offset", 0)
    offset = int(raw_offset)
    if offset < 0:
        raise ValueError("negative Telegram update offset")
except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
    print(f"Invalid bot_state.json offset; resetting to 0: {exc}", flush=True)
    offset = 0
    state = {}
state["offset"] = offset
cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": "", "pending_url": ""}
allowed_chats = {CHAT_ID}
if CHANNEL_ID:
    allowed_chats.add(CHANNEL_ID)

deadline = time.time() + 210
dirty = False
consecutive_409 = 0

while time.time() < deadline:
    try:
        response = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25)
        try:
            resp = response.json()
        except ValueError:
            print(f"Telegram getUpdates returned non-JSON HTTP {response.status_code}: {response.text[:500]}", flush=True)
            time.sleep(3)
            continue
        if response.status_code == 409 or resp.get("error_code") == 409:
            consecutive_409 += 1
            print(f"Telegram getUpdates 409 Conflict ({consecutive_409}/3); another poller is active. Retrying in 3s.", flush=True)
            if consecutive_409 >= 3:
                print("Telegram poller exiting cleanly after repeated 409 conflicts; the next scheduled poll will retry.", flush=True)
                break
            time.sleep(3)
            continue
        consecutive_409 = 0
        if not response.ok or not resp.get("ok"):
            description = str(resp.get("description", response.text))
            print(f"Telegram getUpdates API error HTTP {response.status_code}: {description}", flush=True)
            if response.status_code == 400 and "offset" in description.lower():
                offset = 0
                state["offset"] = 0
                with open("bot_state.json", "w", encoding="utf-8") as state_file:
                    json.dump(state, state_file, indent=2)
                print("Reset invalid Telegram offset to 0; retrying.", flush=True)
                continue
            time.sleep(3)
            continue
        updates = resp.get("result", [])
    except SystemExit:
        raise
    except requests.RequestException as exc:
        print(f"Telegram getUpdates network error: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(3)
        continue

    for u in updates:
        offset = u["update_id"] + 1
        dirty = True
        try:
            msg = u.get("message") or u.get("channel_post") or {}
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            user_id = str((msg.get("from") or {}).get("id", ""))

            if chat_id not in allowed_chats and user_id != CHAT_ID:
                continue

            text = (msg.get("text") or msg.get("caption") or "").strip()
            media = msg.get("video") or msg.get("document") or msg.get("animation") or msg.get("video_note")
            if media:
                size_bytes = int(media.get("file_size") or 0)
                caption = (msg.get("caption") or "").strip()
                url_match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s<>]+", caption, re.I)
                media_name = (msg.get("document") or {}).get("file_name") or f"[Telegram]_Clip_{msg.get('message_id', int(time.time()))}.mp4"
                max_media_bytes = 1_950_000_000  # 1.95 GB decimal, below the 2 GB MTProto ceiling.
                if url_match:
                    clean_url = url_match.group(0).rstrip(".,;!?)")
                    queue_video_link(chat_id, clean_url, media_name)
                elif size_bytes <= 0:
                    send_msg(chat_id, "⛔ Not queued: Telegram did not provide a file size. Please resend the video or send its YouTube URL.", MAIN_KEYBOARD)
                elif size_bytes > max_media_bytes:
                    send_msg(chat_id, f"⛔ Not queued: this Telegram attachment is {size_bytes / 1_000_000:.1f} MB. The MTProto loader accepts files up to 1,950 MB.", MAIN_KEYBOARD)
                else:
                    mid = msg.get("message_id")
                    if mid:
                        queue_video_link(chat_id, f"tgmsg:{chat_id}:{mid}", media_name)
                    else:
                        send_msg(chat_id, "⚠️ I could not identify the Telegram message. Please resend it.", MAIN_KEYBOARD)
                continue
            if not text:
                continue

            if command == "/cancel" or text == "❌ Cancel":
                cfg["pending_url"] = ""
                send_msg(chat_id, "❌ Cancelled. Ready for your next command!", MAIN_KEYBOARD)
            elif re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s<>]+", text, re.I):
                match = re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s<>]+", text, re.I)
                url = match.group(0).rstrip(".,;!?)")
                label = (text[:match.start()] + " " + text[match.end():]).strip()
                if len(label) > 2:
                    queue_video_link(chat_id, url, label)
                    cfg["pending_url"] = ""
                else:
                    cfg["pending_url"] = url
                    send_msg(chat_id, "🎬 Link received! Type a custom file name (e.g. GTA6_Police_Chase) OR tap a game tag button below:", GAME_TAG_KEYBOARD)
            elif command == "/menu":
                send_msg(chat_id, "🎮 Owner Control Panel Active — Tap any button below or paste a YouTube gameplay link:", MAIN_KEYBOARD)
            elif cfg.get("pending_url") and not command:
                tag_map = {"🎮 [GTA6]": "GTA6", "🚗 [GTA5]": "GTA5", "🗽 [GTA4]": "GTA4", "⛏️ [Minecraft]": "Minecraft", "🧱 [Roblox]": "Roblox", "🔫 [Valorant]": "Valorant"}
                if text in tag_map:
                    auto_name = f"[{tag_map[text]}]_Gameplay_{int(time.time()) % 10000}.mp4"
                    queue_video_link(chat_id, cfg["pending_url"], auto_name)
                else:
                    queue_video_link(chat_id, cfg["pending_url"], text)
                cfg["pending_url"] = ""
            elif text == "➕ Add Video Link":
                send_msg(chat_id, "📎 Paste any YouTube gameplay link right now (720p/1080p) and I will ask you what to name it!", MAIN_KEYBOARD)
            elif text == "🚀 Make Short Now" or command == "/make":
                dispatch_result = trigger_workflow("auto_upload.yml")
                if dispatch_result == "HTTP 204 Accepted":
                    send_msg(chat_id, f"🚀 GitHub accepted the workflow dispatch ({dispatch_result}). Publishing is not confirmed until the run completes.", MAIN_KEYBOARD)
                else:
                    send_msg(chat_id, f"⚠️ Workflow dispatch was not confirmed: {dispatch_result}", MAIN_KEYBOARD)
            elif text in ["🗑️ Delete Last", "/delete_last"]:
                vid = cfg.get("last_video_id", "")
                if vid:
                    get_yt_service().videos().delete(id=vid).execute()
                    send_msg(chat_id, f"🗑️ Deleted Short {vid} from YouTube.", MAIN_KEYBOARD)
                    cfg["last_video_id"] = ""
                else:
                    send_msg(chat_id, "No recent Short ID found to delete.", MAIN_KEYBOARD)
            elif text in ["🎯 Focus: GTA 6", "🎯 Focus: Auto"] or command == "/focus":
                focus_arg = text.split(None, 1)[1].strip() if command == "/focus" and len(text.split(None, 1)) > 1 else ""
                val = "gta6" if "GTA 6" in text else ("auto" if "Auto" in text else focus_arg.lower() or "auto")
                cfg["focus"] = val
                send_msg(chat_id, f"🎯 Focus mode switched to: {val.upper()}", MAIN_KEYBOARD)
            elif text in ["🔥 Live Hype", "/hype"]:
                send_msg(chat_id, "🔥 Live US Gaming Hype Radar:\n• " + get_live_hype(), MAIN_KEYBOARD)
            elif text == "📊 Cloud Status" or command == "/status":
                conf = os.environ.get("RCLONE_CONF", "").strip()
                os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
                open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)
                try:
                    m_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "mega:GTA_Clips"]).decode()))
                except Exception:
                    m_cnt = 0
                try:
                    p_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "pcloud:GTA_Clips"]).decode()))
                except Exception:
                    p_cnt = 0
                hist_cnt = len(json.load(open("history.json")).get("used_windows", [])) if os.path.exists("history.json") else 0
                send_msg(chat_id, f"📊 Cloud & Pipeline Status:\n• MEGA videos: {m_cnt}\n• pCloud videos: {p_cnt}\n• Unique cuts used: {hist_cnt}\n• Focus: {cfg.get('focus', 'auto').upper()}", MAIN_KEYBOARD)
            elif text in ["📈 YT Stats", "/stats"]:
                try:
                    yt = get_yt_service()
                    ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
                    send_msg(chat_id, f"📈 Live YouTube Studio Stats:\n• Subscribers: {ch.get('subscriberCount')}\n• Total Views: {ch.get('viewCount')}\n• Videos: {ch.get('videoCount')}", MAIN_KEYBOARD)
                except Exception:
                    hist_cnt = len(json.load(open("history.json")).get("used_windows", [])) if os.path.exists("history.json") else 0
                    last_v = cfg.get("last_video_id") or "None yet"
                    send_msg(chat_id, f"📈 Pipeline Upload Stats:\n• Total Shorts Auto-Published: {hist_cnt}\n• Latest Short: https://youtube.com/shorts/{last_v}\n(Note: Refresh token is upload-only; re-auth with youtube.readonly scope if you want live sub counts here)", MAIN_KEYBOARD)
            elif text in ["❓ Help", "/help", "/start"] or command in ["/help", "/start"]:
                send_msg(chat_id, "🎮 Owner Control Panel Active — Tap any button below or paste a YouTube gameplay link:", MAIN_KEYBOARD)
        except Exception as err:
            send_msg(CHAT_ID, f"⚠️ Command error: {err}", MAIN_KEYBOARD)

    if dirty:
        state["offset"] = offset
        with open("bot_state.json", "w", encoding="utf-8") as state_file:
            json.dump(state, state_file, indent=2)
        with open("config.json", "w", encoding="utf-8") as config_file:
            json.dump(cfg, config_file, indent=2)

subprocess.run(["git", "config", "user.name", "OwnerBot"], check=False)
subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
subprocess.run(["git", "add", "links.txt", "config.json", "tg_offset.txt"], check=False)
subprocess.run(["git", "commit", "-m", "Telegram state sync"], check=False)
if GH_PAT:
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
    push_result = subprocess.run(["git", "push", f"https://x-access-token:{GH_PAT}@github.com/{REPO}.git"], capture_output=True, text=True)
    if push_result.returncode:
        print(f"Telegram state push failed: {push_result.stderr[-1000:]}", flush=True)
print(f"Telegram poller finished cleanly; next offset={offset}", flush=True)
