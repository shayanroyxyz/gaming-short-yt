import os, re, json, subprocess, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
RCLONE_CONF = os.environ.get("RCLONE_CONF", "").strip()

def notify(msg):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg}, timeout=15)

if not os.path.exists("links.txt"):
    exit(0)

lines = [l.strip() for l in open("links.txt") if "|" in l and l.strip().startswith("http")]
if not lines:
    exit(0)

os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(RCLONE_CONF)
subprocess.run(["pip", "install", "-U", "yt-dlp"], check=False)

remaining = []
for line in lines:
    url, fname = [x.strip() for x in line.split("|", 1)]
    safe_name = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", fname)
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    local_file = f"/tmp/{safe_name}"
    if os.path.exists(local_file):
        os.remove(local_file)

    ok = False
    for client in ["android,ios", "tv_embedded,web", "mweb,android"]:
        cmd = [
            "yt-dlp",
            "--extractor-args", f"youtube:player_client={client}",
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-o", local_file,
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(local_file) and os.path.getsize(local_file) > 500000:
            ok = True
            break

    if ok:
        subprocess.run(["rclone", "copyto", local_file, f"mega:GTA_Clips/{safe_name}"], check=False)
        subprocess.run(["rclone", "copyto", local_file, f"pcloud:GTA_Clips/{safe_name}"], check=False)
        os.remove(local_file)
        notify(f"✅ Loaded 720p gameplay to MEGA & pCloud:\n📁 {safe_name}")
    else:
        err_tail = (res.stderr or "")[-180:].strip()
        notify(f"⚠️ Failed to download link: {url}\nReason: {err_tail or 'YouTube IP block - try another link'}")

open("links.txt", "w").write("")
