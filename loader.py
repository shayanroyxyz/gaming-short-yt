import os, subprocess, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
def tg(t):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": t}, timeout=15)

if not os.path.exists("links.txt"):
    open("links.txt", "w").write("")
    exit(0)

lines = [l.strip() for l in open("links.txt").readlines() if l.strip() and not l.startswith("#")]
if not lines:
    print("links.txt is empty; nothing to download.")
    exit(0)

conf = os.environ.get("RCLONE_CONF", "").strip()
os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)

cookies = os.environ.get("YOUTUBE_COOKIES", "").strip()
if cookies:
    open("cookies.txt", "w").write(cookies)

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
