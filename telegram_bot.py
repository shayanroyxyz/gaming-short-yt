import os, re, json, time, subprocess, xml.etree.ElementTree as ET, requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
GH_PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "shayanroyxyz/gta-shorts-agent")

CONTROL_MENU = {
    "inline_keyboard": [
        [{"text": "🚀 Make Short Now", "callback_data": "MAKE_NOW"}, {"text": "🔥 Live Hype", "callback_data": "HYPE"}],
        [{"text": "📊 Cloud Status", "callback_data": "STATUS"}, {"text": "📈 YT Stats", "callback_data": "STATS"}],
        [{"text": "🎯 Focus: GTA 6", "callback_data": "FOCUS_gta6"}, {"text": "🎯 Focus: Auto", "callback_data": "FOCUS_auto"}],
        [{"text": "🗑️ Delete Last Short", "callback_data": "DELETE_LAST"}]
    ]
}

GAME_TAG_BUTTONS = {
    "inline_keyboard": [
        [{"text": "🎮 [GTA6]", "callback_data": "TAG_GTA6"}, {"text": "🚗 [GTA5]", "callback_data": "TAG_GTA5"}, {"text": "🗽 [GTA4]", "callback_data": "TAG_GTA4"}],
        [{"text": "⛏️ [Minecraft]", "callback_data": "TAG_Minecraft"}, {"text": "🧱 [Roblox]", "callback_data": "TAG_Roblox"}, {"text": "🔫 [Valorant]", "callback_data": "TAG_Valorant"}]
    ]
}

def send_msg(text, reply_markup=None):
    if TOKEN and CHAT_ID:
        payload = {"chat_id": CHAT_ID, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload, timeout=15)

def trigger_workflow(wf_file):
    if GH_PAT:
        requests.post(
            f"https://api.github.com/repos/{REPO}/actions/workflows/{wf_file}/dispatches",
            headers={"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"},
            json={"ref": "main"},
            timeout=15
        )

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
    for q in ["GTA+6", "GTA+5+mods", "Minecraft", "Roblox", "Valorant"]:
        try:
            r = requests.get(f"https://news.google.com/rss/search?q={q}+gaming+when:2d&hl=en-US&gl=US&ceid=US:en", timeout=10)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item")[:2]:
                headlines.append(item.find("title").text.split(" - ")[0])
        except Exception:
            pass
    return "\n• ".join(headlines[:8]) if headlines else "GTA 6 Free Roam, GTA 4 vs GTA 6 Physics, Minecraft Impossible Tricks"

def queue_video_link(url, raw_name):
    safe_name = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", raw_name.strip())
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    with open("links.txt", "a") as f:
        f.write(f"{url} | {safe_name}\n")
    send_msg(f"✅ Queued for 0-Byte Cloud Download:\nFile: {safe_name}\nLoading into MEGA/pCloud now!", CONTROL_MENU)

if not TOKEN or not CHAT_ID:
    print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set yet; exiting cleanly.")
    exit(0)

offset = int(open("tg_offset.txt").read().strip()) if os.path.exists("tg_offset.txt") else 0
updates = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 5}, timeout=15).json().get("result", [])
cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": "", "pending_url": ""}

for u in updates:
    offset = u["update_id"] + 1
    msg = u.get("message") or {}
    cb = u.get("callback_query") or {}
    sender = str((msg.get("chat") or cb.get("message", {}).get("chat") or {}).get("id", ""))
    if sender != CHAT_ID:
        continue

    text = (msg.get("text") or cb.get("data") or "").strip()
    if cb:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", data={"callback_query_id": cb["id"]})

    if "youtu.be/" in text or "youtube.com/" in text:
        parts = text.split(None, 1)
        url = parts[0]
        if len(parts) > 1 and len(parts[1].strip()) > 2:
            queue_video_link(url, parts[1])
            cfg["pending_url"] = ""
        else:
            cfg["pending_url"] = url
            send_msg("🎬 Link received! What should I name this file?\n\nReply with a custom name (e.g. GTA6_Police_Chase) OR tap a quick game tag below:", GAME_TAG_BUTTONS)
    elif text.startswith("TAG_") and cfg.get("pending_url"):
        tag = text.replace("TAG_", "")
        auto_name = f"[{tag}]_Gameplay_{int(time.time()) % 10000}.mp4"
        queue_video_link(cfg["pending_url"], auto_name)
        cfg["pending_url"] = ""
    elif cfg.get("pending_url") and not text.startswith("/") and text not in ["MAKE_NOW", "HYPE", "STATUS", "STATS", "DELETE_LAST"]:
        queue_video_link(cfg["pending_url"], text)
        cfg["pending_url"] = ""
    elif text in ["/make", "MAKE_NOW"]:
        trigger_workflow("auto_upload.yml")
        send_msg("🚀 Creating & publishing a new Short right now! Video will arrive here in ~60 seconds.", CONTROL_MENU)
    elif text in ["/delete_last", "DELETE_LAST"]:
        vid = cfg.get("last_video_id", "")
        if vid:
            try:
                get_yt_service().videos().delete(id=vid).execute()
                send_msg(f"🗑️ Deleted Short {vid} from YouTube.", CONTROL_MENU)
                cfg["last_video_id"] = ""
            except Exception as e:
                send_msg(f"Delete error: {e}", CONTROL_MENU)
        else:
            send_msg("No recent Short ID found to delete.", CONTROL_MENU)
    elif text.startswith("/focus") or text.startswith("FOCUS_"):
        val = text.replace("/focus", "").replace("FOCUS_", "").strip().lower() or "auto"
        cfg["focus"] = val
        send_msg(f"🎯 Focus mode set to: {val.upper()}", CONTROL_MENU)
    elif text in ["/hype", "HYPE"]:
        send_msg("🔥 Live US Gaming Hype Radar:\n• " + get_live_hype() + "\n\nPaste any YouTube link here to add footage!", CONTROL_MENU)
    elif text in ["/status", "STATUS"]:
        conf = os.environ.get("RCLONE_CONF", "").strip()
        os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
        open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)
        m_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "mega:GTA_Clips"]).decode()))
        p_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "pcloud:GTA_Clips"]).decode()))
        hist_cnt = len(json.load(open("history.json")).get("used_windows", [])) if os.path.exists("history.json") else 0
        send_msg(f"📊 Cloud & Pipeline Status:\n• MEGA: {m_cnt} videos\n• pCloud: {p_cnt} videos\n• Unique cuts used: {hist_cnt}\n• Focus: {cfg.get('focus', 'auto').upper()}", CONTROL_MENU)
    elif text in ["/stats", "STATS"]:
        yt = get_yt_service()
        ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
        send_msg(f"📈 Live YouTube Studio Stats:\n• Subscribers: {ch.get('subscriberCount')}\n• Total Views: {ch.get('viewCount')}\n• Videos: {ch.get('videoCount')}", CONTROL_MENU)
    else:
        send_msg("🎮 Owner Control Panel — Choose an action or paste a YouTube gameplay link:", CONTROL_MENU)

open("tg_offset.txt", "w").write(str(offset))
json.dump(cfg, open("config.json", "w"), indent=2)
