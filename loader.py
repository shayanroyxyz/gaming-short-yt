import os, re, shutil, subprocess, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
RCLONE_CONF = os.environ.get("RCLONE_CONF", "").strip()
YT_COOKIES = os.environ.get("YT_COOKIES", "").strip()
TG_API = os.environ.get("TG_API_BASE", "https://api.telegram.org").rstrip("/")

def notify(msg):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg}, timeout=15)

if not os.path.exists("links.txt"):
    exit(0)

lines = [l.strip() for l in open("links.txt") if "|" in l and (l.strip().startswith("http") or l.strip().startswith("tgfile:"))]
if not lines:
    exit(0)

os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(RCLONE_CONF)
if YT_COOKIES:
    open("/tmp/cookies.txt", "w").write(YT_COOKIES)

for line in lines:
    src, fname = [x.strip() for x in line.split("|", 1)]
    safe_name = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", fname)
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    local_file = f"/tmp/{safe_name}"
    if os.path.exists(local_file):
        os.remove(local_file)

    ok = False
    if src.startswith("tgfile:"):
        fid = src.split(":", 1)[1].strip()
        try:
            r = requests.get(f"{TG_API}/bot{TOKEN}/getFile", params={"file_id": fid}, timeout=60).json()
            fpath = (r.get("result") or {}).get("file_path", "")
            if fpath and os.path.exists(fpath):
                shutil.copy2(fpath, local_file)
                ok = True
            elif fpath:
                with requests.get(f"{TG_API}/file/bot{TOKEN}/{fpath}", stream=True, timeout=300) as s:
                    s.raise_for_status()
                    with open(local_file, "wb") as f:
                        for chunk in s.iter_content(chunk_size=1024 * 1024):
                            if chunk: f.write(chunk)
                ok = os.path.exists(local_file) and os.path.getsize(local_file) > 100000
        except Exception as e:
            notify(f"⚠️ Telegram file fetch error: {e}")
    else:
        subprocess.run(["pip", "install", "-q", "-U", "yt-dlp"], check=False)
        cmd = ["yt-dlp", "-f", "best[height<=720][ext=mp4]/best[height<=720]", "--no-playlist", "-o", local_file, src]
        if YT_COOKIES:
            cmd[1:1] = ["--cookies", "/tmp/cookies.txt"]
        subprocess.run(cmd, check=False)
        ok = os.path.exists(local_file) and os.path.getsize(local_file) > 500000

    if ok:
        subprocess.run(["rclone", "copyto", local_file, f"mega:GTA_Clips/{safe_name}"], check=False)
        subprocess.run(["rclone", "copyto", local_file, f"pcloud:GTA_Clips/{safe_name}"], check=False)
        os.remove(local_file)
        notify(f"✅ Saved to MEGA & pCloud:\n📁 {safe_name}")
    elif not src.startswith("tgfile:"):
        notify(f"⚠️ YouTube link blocked on datacenter IP: {src}\nForward the video from @gozillabot_downloaderbot_bot or upload from Snaptube instead!")

open("links.txt", "w").write("")
