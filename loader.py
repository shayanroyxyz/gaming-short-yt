import os, re, json, subprocess, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
RCLONE_CONF = os.environ.get("RCLONE_CONF", "").strip()
YT_COOKIES = os.environ.get("YT_COOKIES", "").strip()

def notify(msg):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg}, timeout=15)

def extract_vid_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else ""

def download_via_cobalt(url, out_path):
    instances = [
        "https://api.cobalt.tools/",
        "https://cobalt-api.kwiatekmiki.com/",
        "https://co.wuk.sh/"
    ]
    for api in instances:
        try:
            r = requests.post(
                api,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"url": url, "videoQuality": "720", "filenameStyle": "basic"},
                timeout=20
            )
            if r.status_code == 200:
                dl_url = r.json().get("url")
                if dl_url:
                    with requests.get(dl_url, stream=True, timeout=180) as s:
                        s.raise_for_status()
                        with open(out_path, "wb") as f:
                            for chunk in s.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 500000:
                        return True
        except Exception:
            pass
    return False

def download_via_piped(vid_id, out_path):
    if not vid_id:
        return False
    mirrors = ["https://pipedapi.kavin.rocks", "https://pipedapi.adminforge.de", "https://api.piped.yt"]
    for m in mirrors:
        try:
            data = requests.get(f"{m}/streams/{vid_id}", timeout=15).json()
            v_streams = [s for s in data.get("videoStreams", []) if s.get("format") == "MPEG_4" and not s.get("videoOnly")]
            v_streams.sort(key=lambda x: int(re.sub(r"\D", "", x.get("quality", "0")) or 0), reverse=True)
            pick = next((s for s in v_streams if "720" in s.get("quality", "")), v_streams[0] if v_streams else None)
            if pick and pick.get("url"):
                with requests.get(pick["url"], stream=True, timeout=180) as s:
                    s.raise_for_status()
                    with open(out_path, "wb") as f:
                        for chunk in s.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 500000:
                    return True
        except Exception:
            pass
    return False

if not os.path.exists("links.txt"):
    exit(0)

lines = [l.strip() for l in open("links.txt") if "|" in l and l.strip().startswith("http")]
if not lines:
    exit(0)

os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(RCLONE_CONF)

if YT_COOKIES:
    open("/tmp/cookies.txt", "w").write(YT_COOKIES)

for line in lines:
    url, fname = [x.strip() for x in line.split("|", 1)]
    safe_name = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", fname)
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    local_file = f"/tmp/{safe_name}"
    if os.path.exists(local_file):
        os.remove(local_file)

    vid_id = extract_vid_id(url)
    ok = download_via_cobalt(url, local_file) or download_via_piped(vid_id, local_file)

    if not ok:
        subprocess.run(["pip", "install", "-q", "-U", "yt-dlp"], check=False)
        cmd = ["yt-dlp", "-f", "best[height<=720][ext=mp4]/best[height<=720]", "--no-playlist", "-o", local_file, url]
        if YT_COOKIES:
            cmd[1:1] = ["--cookies", "/tmp/cookies.txt"]
        subprocess.run(cmd, check=False)
        ok = os.path.exists(local_file) and os.path.getsize(local_file) > 500000

    if ok:
        subprocess.run(["rclone", "copyto", local_file, f"mega:GTA_Clips/{safe_name}"], check=False)
        subprocess.run(["rclone", "copyto", local_file, f"pcloud:GTA_Clips/{safe_name}"], check=False)
        os.remove(local_file)
        notify(f"✅ Loaded 720p gameplay to MEGA & pCloud:\n📁 {safe_name}")
    else:
        notify(f"⚠️ YouTube blocked datacenter IP for: {url}\nTip: Add YT_COOKIES in GitHub Secrets once for 100% success on any link.")

open("links.txt", "w").write("")
