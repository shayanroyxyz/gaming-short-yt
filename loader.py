import os, re, json, asyncio, random, subprocess, requests
from telethon import TelegramClient

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = int(str(os.environ.get("TELEGRAM_CHAT_ID", "0")).strip() or 0)
API_ID = int(str(os.environ.get("TG_API_ID", "0")).strip() or 0)
API_HASH = os.environ.get("TG_API_HASH", "").strip()
RCLONE_CONF = os.environ.get("RCLONE_CONF", "").strip()
YT_COOKIES = os.environ.get("YT_COOKIES", "").strip()

def notify(msg):
    if TOKEN and CHAT_ID:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg}, timeout=20)

def get_cloud_stats(remote):
    try:
        out = subprocess.check_output(["rclone", "about", f"{remote}:", "--json"], text=True, timeout=60)
        d = json.loads(out)
        total = d.get("total", 0) / (1024**3)
        used = d.get("used", 0) / (1024**3)
        free = d.get("free", max(0, d.get("total", 0) - d.get("used", 0))) / (1024**3)
        return round(used, 2), round(free, 2), round(total, 2)
    except Exception:
        return 0.0, 0.0, 0.0

def count_clips(remote):
    try:
        out = subprocess.check_output(["rclone", "lsf", f"{remote}:GTA_Clips"], text=True, timeout=20)
        return len([x for x in out.splitlines() if x.strip().endswith(".mp4")])
    except Exception:
        return 0

async def download_tg_msg(cid, mid, out_path):
    client = TelegramClient("/tmp/bot_mtproto", API_ID, API_HASH)
    await client.start(bot_token=TOKEN)
    try:
        msg = await client.get_messages(cid, ids=mid)
        if not msg or not msg.media:
            return False, "Message or video not found in chat"
        await client.download_media(msg, file=out_path)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
            return True, ""
        return False, "Downloaded file empty"
    finally:
        await client.disconnect()

if not os.path.exists("links.txt"):
    exit(0)

lines = [l.strip() for l in open("links.txt") if "|" in l and l.strip()]
if not lines:
    exit(0)

os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(RCLONE_CONF)
if YT_COOKIES:
    open("/tmp/cookies.txt", "w").write(YT_COOKIES)

processed = set()
for line in lines:
    processed.add(line)
    src, fname = [x.strip() for x in line.split("|", 1)]
    safe_name = re.sub(r"[^a-zA-Z0-9_\[\]-]", "_", fname)
    if not safe_name.endswith(".mp4"):
        safe_name += ".mp4"
    local_file = f"/tmp/{safe_name}"
    if os.path.exists(local_file):
        os.remove(local_file)

    ok = False
    err_detail = ""
    if src.startswith("tgmsg:"):
        if not API_ID or not API_HASH:
            err_detail = "TG_API_ID or TG_API_HASH secret missing in GitHub"
        else:
            try:
                _, c_str, m_str = src.split(":")
                ok, err_detail = asyncio.run(download_tg_msg(int(c_str), int(m_str), local_file))
            except Exception as e:
                err_detail = str(e)
    elif src.startswith("http"):
        subprocess.run(["pip", "install", "-q", "-U", "yt-dlp"], check=False)
        cmd = ["yt-dlp", "-f", "best[height<=720][ext=mp4]/best[height<=720]", "--no-playlist", "-o", local_file, src]
        if YT_COOKIES:
            cmd[1:1] = ["--cookies", "/tmp/cookies.txt"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        ok = os.path.exists(local_file) and os.path.getsize(local_file) > 500000
        if not ok:
            err_detail = (res.stderr or "YouTube IP blocked")[-140:].strip()

    if ok:
        fsize_mb = round(os.path.getsize(local_file) / (1024**2), 1)
        m_used, m_free, m_tot = get_cloud_stats("mega")
        p_used, p_free, p_tot = get_cloud_stats("pcloud")

        candidates = []
        if m_free > 0.5 or m_tot == 0: candidates.append("mega")
        if p_free > 0.5 or p_tot == 0: candidates.append("pcloud")
        target = random.choice(candidates) if candidates else "mega"

        res = subprocess.run(["rclone", "copyto", local_file, f"{target}:GTA_Clips/{safe_name}"], capture_output=True, text=True)
        if res.returncode != 0:
            alt = "pcloud" if target == "mega" else "mega"
            res2 = subprocess.run(["rclone", "copyto", local_file, f"{alt}:GTA_Clips/{safe_name}"], capture_output=True, text=True)
            if res2.returncode == 0:
                target = alt
            else:
                notify(f"❌ rclone upload failed for {safe_name}:\nMEGA: {res.stderr[-120:]}\npCloud: {res2.stderr[-120:]}")
                os.remove(local_file)
                continue

        os.remove(local_file)
        m_used, m_free, m_tot = get_cloud_stats("mega")
        p_used, p_free, p_tot = get_cloud_stats("pcloud")
        m_cnt, p_cnt = count_clips("mega"), count_clips("pcloud")
        tot_free = round(m_free + p_free, 2)
        tot_cap = round(m_tot + p_tot, 2)

        notify(
            f"✅ Unique Upload Complete!\n"
            f"📁 File: {safe_name} ({fsize_mb} MB)\n"
            f"☁️ Saved Exclusively To: {target.upper()}\n\n"
            f"📊 Cloud Storage & Video Pool:\n"
            f"• MEGA ({m_cnt} videos): {m_used} GB used | {m_free} GB left (of {m_tot} GB)\n"
            f"• pCloud ({p_cnt} videos): {p_used} GB used | {p_free} GB left (of {p_tot} GB)\n"
            f"🔋 Combined Left: {tot_free} GB / {tot_cap} GB"
        )
    else:
        notify(f"⚠️ Failed to transfer {safe_name}:\nReason: {err_detail}")

# Remove only processed lines so new lines queued mid-run are preserved
if os.path.exists("links.txt"):
    latest = [l.strip() for l in open("links.txt") if l.strip()]
    remaining = [l for l in latest if l not in processed]
    open("links.txt", "w").write(("\n".join(remaining) + "\n") if remaining else "")
