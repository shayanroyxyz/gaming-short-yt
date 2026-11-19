import os, json, subprocess, xml.etree.ElementTree as ET, requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
GH_PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "shayanroyxyz/gta-shorts-agent")

def send_msg(text):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text}, timeout=15)

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

if not TOKEN or not CHAT_ID:
    exit(0)

offset = int(open("tg_offset.txt").read().strip()) if os.path.exists("tg_offset.txt") else 0
updates = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 5}, timeout=15).json().get("result", [])

cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": ""}

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
        with open("links.txt", "a") as f:
            f.write(text + "\n")
        send_msg(f"✅ Added to cloud queue! Downloading 720p directly into MEGA/pCloud (0 MB phone data):\n{text}")
    elif text == "/make" or text == "MAKE_NOW":
        trigger_workflow("auto_upload.yml")
        send_msg("🚀 Triggered a brand-new Short right now! Will deliver here in ~60 seconds.")
    elif text == "/delete_last" or text == "DELETE_LAST":
        vid = cfg.get("last_video_id", "")
        if vid:
            try:
                get_yt_service().videos().delete(id=vid).execute()
                send_msg(f"🗑️ Deleted Short {vid} from YouTube.")
                cfg["last_video_id"] = ""
            except Exception as e:
                send_msg(f"Delete error: {e}")
        else:
            send_msg("No recent video ID stored.")
    elif text.startswith("/focus"):
        val = text.replace("/focus", "").strip().lower() or "auto"
        cfg["focus"] = val
        send_msg(f"🎯 Focus updated to: {val.upper()}\nExamples: /focus gta6, /focus physics, /focus minecraft, /focus auto")
    elif text == "/hype":
        send_msg("🔥 Live US Gaming Hype Radar:\n• " + get_live_hype() + "\n\nTip: Send a YouTube link matching one of these topics!")
    elif text == "/status":
        conf = os.environ.get("RCLONE_CONF", "").strip()
        os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
        open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)
        m_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "mega:GTA_Clips"]).decode()))
        p_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "pcloud:GTA_Clips"]).decode()))
        hist_cnt = len(json.load(open("history.json")).get("used_windows", [])) if os.path.exists("history.json") else 0
        send_msg(f"📊 Pipeline Status:\n• MEGA videos: {m_cnt}\n• pCloud videos: {p_cnt}\n• Unique cuts used: {hist_cnt}\n• Current Focus: {cfg.get('focus', 'auto').upper()}")
    elif text == "/stats" or text == "STATS":
        yt = get_yt_service()
        ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
        send_msg(f"📈 Channel Stats:\n• Subscribers: {ch.get('subscriberCount')}\n• Total Views: {ch.get('viewCount')}\n• Videos: {ch.get('videoCount')}")
    elif text == "/help" or text == "/start":
        send_msg("🤖 Owner Commands:\n• Paste any YouTube link + [GAME]_Name.mp4 to load into cloud\n• /make — Publish a Short immediately\n• /hype — Live US trending gaming topics\n• /focus gta6 | physics | minecraft | auto\n• /status — Cloud storage & clip count\n• /stats — Live YouTube subs & views\n• /delete_last — Remove last uploaded Short")

open("tg_offset.txt", "w").write(str(offset))
json.dump(cfg, open("config.json", "w"), indent=2)
