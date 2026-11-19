python3 -c '
import os, json
os.makedirs(".github/workflows", exist_ok=True)

if not os.path.exists("config.json"):
    json.dump({"focus": "auto", "last_video_id": "", "pending_url": ""}, open("config.json", "w"), indent=2)

if not os.path.exists("links.txt"):
    open("links.txt", "w").write("")

# 1. Telegram Command Center (Polls every 5 mins + manual)
tg_yml = """name: Telegram Owner Command Center
on:
  schedule:
    - cron: \x27*/5 * * * *\x27
  workflow_dispatch:
jobs:
  listen:
    if: github.repository == \x27shayanroyxyz/gta-shorts-agent\x27
    runs-on: ubuntu-latest
    timeout-minutes: 4
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get update && sudo apt-get install -y rclone
      - run: pip install -q requests google-api-python-client google-auth-oauthlib
      - env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          RCLONE_CONF: ${{ secrets.RCLONE_CONF }}
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
          YOUTUBE_CLIENT_SECRET: ${{ secrets.YOUTUBE_CLIENT_SECRET }}
          YOUTUBE_REFRESH_TOKEN: ${{ secrets.YOUTUBE_REFRESH_TOKEN }}
          GH_PAT: ${{ secrets.GH_PAT }}
        run: python telegram_bot.py
      - run: |
          git config user.name "OwnerBot"
          git config user.email "bot@users.noreply.github.com"
          git add links.txt config.json tg_offset.txt
          git commit -m "Telegram remote update" || true
          git push https://x-access-token:${{ secrets.GH_PAT }}@github.com/${{ github.repository }}.git || true
"""
open(".github/workflows/telegram_listener.yml", "w").write(tg_yml)

# 2. 0-Byte Cloud Video Loader (Runs automatically when links.txt updates)
loader_yml = """name: 0-Byte Cloud Video Loader
on:
  push:
    paths:
      - \x27links.txt\x27
  workflow_dispatch:
jobs:
  load:
    if: github.repository == \x27shayanroyxyz/gta-shorts-agent\x27
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg rclone
      - run: pip install -q yt-dlp[default] requests
      - env:
          RCLONE_CONF: ${{ secrets.RCLONE_CONF }}
          YOUTUBE_COOKIES: ${{ secrets.YOUTUBE_COOKIES }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python loader.py
      - run: |
          git config user.name "LoaderBot"
          git config user.email "bot@users.noreply.github.com"
          git add links.txt
          git commit -m "Clear processed links" || true
          git push https://x-access-token:${{ secrets.GH_PAT }}@github.com/${{ github.repository }}.git || true
"""
open(".github/workflows/load_links.yml", "w").write(loader_yml)

# 3. 6x Daily US Prime-Time Auto-Publisher
main_yml = """name: 24/7 US Viral Gaming Shorts (6x Daily)
on:
  schedule:
    - cron: \x2717 3 * * *\x27
    - cron: \x2717 7 * * *\x27
    - cron: \x2717 12 * * *\x27
    - cron: \x2717 16 * * *\x27
    - cron: \x2717 19 * * *\x27
    - cron: \x2717 22 * * *\x27
  workflow_dispatch:
jobs:
  run-bot:
    if: github.repository == \x27shayanroyxyz/gta-shorts-agent\x27
    runs-on: ubuntu-latest
    timeout-minutes: 8
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: \x273.11\x27
      - run: sudo apt-get update && sudo apt-get install -y ffmpeg fonts-dejavu-core rclone
      - run: pip install -q google-api-python-client google-auth-oauthlib google-genai edge-tts requests
      - env:
          RCLONE_CONF: ${{ secrets.RCLONE_CONF }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
          YOUTUBE_CLIENT_SECRET: ${{ secrets.YOUTUBE_CLIENT_SECRET }}
          YOUTUBE_REFRESH_TOKEN: ${{ secrets.YOUTUBE_REFRESH_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main.py
      - run: |
          git config user.name "AutoBot"
          git config user.email "bot@users.noreply.github.com"
          git add history.json config.json
          git commit -m "Log clip history & last video" || true
          git push https://x-access-token:${{ secrets.GH_PAT }}@github.com/${{ github.repository }}.git || true
"""
open(".github/workflows/auto_upload.yml", "w").write(main_yml)

# 4. telegram_bot.py (Interactive Control Buttons + Link Naming Prompt)
tg_py = """import os, re, json, time, subprocess, xml.etree.ElementTree as ET, requests
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
    return "\\n• ".join(headlines[:8]) if headlines else "GTA 6 Free Roam, GTA 4 vs GTA 6 Physics, Minecraft Impossible Tricks"

def queue_video_link(url, raw_name):
    safe_name = re.sub(r"[^a-zA-Z0-9_\\[\\]-]", "_", raw_name.strip())
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    with open("links.txt", "a") as f:
        f.write(f"{url} | {safe_name}\\n")
    send_msg(f"✅ Queued for 0-Byte Cloud Download:\\nFile: {safe_name}\\nLoading into MEGA/pCloud now!", CONTROL_MENU)

if not TOKEN or not CHAT_ID:
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

    # 1. User sent a YouTube link -> Save & Ask for File Name / Game Tag
    if "youtu.be/" in text or "youtube.com/" in text:
        parts = text.split(None, 1)
        url = parts[0]
        if len(parts) > 1 and len(parts[1].strip()) > 2:
            queue_video_link(url, parts[1])
            cfg["pending_url"] = ""
        else:
            cfg["pending_url"] = url
            send_msg("🎬 Link received! What should I name this file?\\n\\nReply with a custom name (e.g. GTA6_Police_Chase) OR tap a quick game tag below:", GAME_TAG_BUTTONS)

    # 2. User tapped a quick game tag button for pending link
    elif text.startswith("TAG_") and cfg.get("pending_url"):
        tag = text.replace("TAG_", "")
        auto_name = f"[{tag}]_Gameplay_{int(time.time()) % 10000}.mp4"
        queue_video_link(cfg["pending_url"], auto_name)
        cfg["pending_url"] = ""

    # 3. User replied with a custom filename for pending link
    elif cfg.get("pending_url") and not text.startswith("/") and text not in ["MAKE_NOW", "HYPE", "STATUS", "STATS", "DELETE_LAST"]:
        queue_video_link(cfg["pending_url"], text)
        cfg["pending_url"] = ""

    # 4. Control Buttons & Commands
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
        send_msg("🔥 Live US Gaming Hype Radar:\\n• " + get_live_hype() + "\\n\\nPaste any YouTube link here to add footage!", CONTROL_MENU)
    elif text in ["/status", "STATUS"]:
        conf = os.environ.get("RCLONE_CONF", "").strip()
        os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
        open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)
        m_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "mega:GTA_Clips"]).decode()))
        p_cnt = len(json.loads(subprocess.check_output(["rclone", "lsjson", "pcloud:GTA_Clips"]).decode()))
        hist_cnt = len(json.load(open("history.json")).get("used_windows", [])) if os.path.exists("history.json") else 0
        send_msg(f"📊 Cloud & Pipeline Status:\\n• MEGA: {m_cnt} videos\\n• pCloud: {p_cnt} videos\\n• Unique cuts used: {hist_cnt}\\n• Focus: {cfg.get(\x27focus\x27, \x27auto\x27).upper()}", CONTROL_MENU)
    elif text in ["/stats", "STATS"]:
        yt = get_yt_service()
        ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
        send_msg(f"📈 Live YouTube Studio Stats:\\n• Subscribers: {ch.get(\x27subscriberCount\x27)}\\n• Total Views: {ch.get(\x27viewCount\x27)}\\n• Videos: {ch.get(\x27videoCount\x27)}", CONTROL_MENU)
    else:
        send_msg("🎮 Owner Control Panel — Choose an action or paste a YouTube gameplay link:", CONTROL_MENU)

open("tg_offset.txt", "w").write(str(offset))
json.dump(cfg, open("config.json", "w"), indent=2)
"""
open("telegram_bot.py", "w").write(tg_py)

# 5. loader.py (Downloads 720p in Cloud -> MEGA/pCloud -> Clears links.txt)
loader_py = """import os, subprocess, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
def tg(t):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": t}, timeout=15)

conf = os.environ.get("RCLONE_CONF", "").strip()
os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)

cookies = os.environ.get("YOUTUBE_COOKIES", "").strip()
if cookies:
    open("cookies.txt", "w").write(cookies)

lines = [l.strip() for l in open("links.txt").readlines() if l.strip() and not l.startswith("#")]
for idx, line in enumerate(lines):
    parts = [p.strip() for p in line.split("|")]
    url = parts[0].strip()
    fname = parts[1].strip() if len(parts) > 1 else f"[GTA]_Gameplay_{idx+1}.mp4"
    if not fname.endswith(".mp4"):
        fname += ".mp4"
    cmd = ["yt-dlp", "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b", "--merge-output-format", "mp4", "-o", fname, url]
    if cookies:
        cmd.extend(["--cookies", "cookies.txt"])
    res = subprocess.run(cmd)
    if res.returncode == 0 and os.path.exists(fname):
        up = subprocess.run(["rclone", "move", fname, "mega:GTA_Clips/"])
        dest = "MEGA"
        if up.returncode != 0:
            subprocess.run(["rclone", "move", fname, "pcloud:GTA_Clips/"], check=True)
            dest = "pCloud"
        tg(f"✅ Loaded 720p gameplay into {dest}: {fname}")
    else:
        tg(f"⚠️ Failed to download link: {url}")

open("links.txt", "w").write("")
"""
open("loader.py", "w").write(loader_py)

# 6. main.py (Complete Auto-Clipper + Randomized Voices/Captions + Telegram Buttons)
main_py = """import os, re, json, time, random, asyncio, textwrap, subprocess, urllib.parse, xml.etree.ElementTree as ET, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai

MALE_US_VOICES = [
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-ChristopherNeural",
    "en-US-GuyNeural"
]

CAPTION_STYLES = [
    "FontName=DejaVu Sans,FontSize=25,Bold=1,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=5",
    "FontName=DejaVu Sans,FontSize=24,Bold=1,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=3,Outline=2,Shadow=0,Alignment=5",
    "FontName=DejaVu Sans,FontSize=25,Bold=1,PrimaryColour=&H0000FF66,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=5",
    "FontName=DejaVu Sans,FontSize=25,Bold=1,PrimaryColour=&H00FFFF00,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=5"
]

def send_telegram_with_buttons(text, video_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    kb = json.dumps({
        "inline_keyboard": [
            [{"text": "🚀 Make Another Now", "callback_data": "MAKE_NOW"}, {"text": "📈 YT Stats", "callback_data": "STATS"}],
            [{"text": "📊 Cloud Status", "callback_data": "STATUS"}, {"text": "🗑️ Delete Last Short", "callback_data": "DELETE_LAST"}]
        ]
    })
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": text, "reply_markup": kb}, timeout=15)
        if video_path and os.path.exists(video_path):
            with open(video_path, "rb") as vf:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat_id, "caption": "Tap Share -> Instagram Reels to cross-post!"},
                    files={"video": vf},
                    timeout=60
                )
    except Exception as e:
        print("Telegram notify skip:", e)

def fetch_live_hype_context():
    topics = []
    for q in ["GTA+6", "GTA+5", "Minecraft", "Roblox", "Valorant"]:
        try:
            r = requests.get(f"https://news.google.com/rss/search?q={q}+gaming+when:2d&hl=en-US&gl=US&ceid=US:en", timeout=8)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item")[:2]:
                topics.append(item.find("title").text.split(" - ")[0])
        except Exception:
            pass
    return "; ".join(topics[:6]) if topics else "GTA 6 realistic open world details and viral gaming physics"

def ask_ai_brain(prompt):
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9},
                timeout=20
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print("Groq fallback:", e)

    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key:
        for mid in ["qwen/qwen-2.5-72b-instruct:free", "deepseek/deepseek-chat-v3-0324:free"]:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    json={"model": mid, "messages": [{"role": "user", "content": prompt}]},
                    timeout=25
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print("OpenRouter fallback:", mid, e)

    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gem_key:
        client = genai.Client(api_key=gem_key)
        return client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text
    raise RuntimeError("No AI API key succeeded.")

def stream_unique_action_clips(hist, focus):
    conf = os.environ.get("RCLONE_CONF", "").strip()
    os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
    open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)

    pool = []
    for remote in ["mega", "pcloud"]:
        try:
            out = subprocess.check_output(["rclone", "lsjson", f"{remote}:GTA_Clips"], stderr=subprocess.DEVNULL).decode()
            for f in json.loads(out):
                if not f.get("IsDir") and f["Name"].lower().endswith((".mp4", ".mkv", ".webm")):
                    pool.append((remote, f["Name"]))
        except Exception:
            pass

    if not pool:
        raise RuntimeError("No videos found in mega:GTA_Clips or pcloud:GTA_Clips! Send a YouTube link to your Telegram bot first.")

    focused = [x for x in pool if focus != "auto" and focus in x[1].lower()]
    if focused:
        remote, fname = random.choice(focused)
    else:
        gta_files = [x for x in pool if "gta" in x[1].lower()]
        remote, fnam
