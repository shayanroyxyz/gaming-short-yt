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
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                data={"chat_id": CHAT_ID, "text": msg}, timeout=20
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"Telegram notification skipped: {type(exc).__name__}: {exc}")

def get_cloud_stats(remote):
    """Return real provider quota in decimal GB, or None when it cannot be verified."""
    try:
        import time
        time.sleep(3)
        res = subprocess.run(
            ["rclone", "about", f"{remote}:", "--json"],
            capture_output=True, text=True, timeout=35
        )
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "unknown rclone error").strip()
            print(f"[{remote}] quota lookup failed (exit {res.returncode}): {detail[-500:]}")
            return None
        data = json.loads(res.stdout or "{}")
        total_bytes, used_bytes = data.get("total"), data.get("used")
        free_bytes = data.get("free")
        if total_bytes is None or used_bytes is None:
            print(f"[{remote}] quota response omitted total/used; refusing to display a fake 0 GB quota.")
            return None
        if free_bytes is None:
            free_bytes = max(0, int(total_bytes) - int(used_bytes))
        if int(total_bytes) <= 0 or int(free_bytes) < 0:
            print(f"[{remote}] quota response invalid: {data}")
            return None
        gb = 1_000_000_000
        return (round(int(used_bytes) / gb, 2),
                round(int(free_bytes) / gb, 2),
                round(int(total_bytes) / gb, 2))
    except Exception as exc:
        print(f"[{remote}] quota lookup exception: {type(exc).__name__}: {exc}")
        return None

def count_clips(remote):
    try:
        import time
        time.sleep(3)
        out = subprocess.check_output(["rclone", "lsf", f"{remote}:GTA_Clips"], text=True, timeout=20)
        return len([x for x in out.splitlines() if x.strip().endswith(".mp4")])
    except Exception:
        return 0

def remote_ready(remote):
    """Return True only when rclone can authenticate to the configured remote."""
    try:
        result = subprocess.run(
            ["rclone", "lsd", f"{remote}:"],
            capture_output=True, text=True, timeout=45
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "remote unavailable").strip()
            print(f"[{remote}] remote unavailable: {detail[-350:]}")
            return False
        return True
    except Exception as exc:
        print(f"[{remote}] remote check failed: {type(exc).__name__}: {exc}")
        return False


def verify_uploaded_file(remote, filename, expected_size):
    try:
        import time
        time.sleep(3)
        raw = subprocess.check_output(
            ["rclone", "lsjson", f"{remote}:GTA_Clips"],
            text=True, stderr=subprocess.PIPE, timeout=60
        )
        for item in json.loads(raw):
            if item.get("Name") == filename and not item.get("IsDir"):
                return int(item.get("Size", -1)) == int(expected_size)
    except Exception as exc:
        print(f"[{remote}] upload verification failed: {type(exc).__name__}: {exc}")
    return False

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
    
    src, fname = [x.strip() for x in line.split("|", 1)]
    stem, ext = os.path.splitext(fname)
    safe_stem = re.sub(r"[^a-zA-Z0-9_\[\]-]+", "_", stem).strip("_") or "clip"
    safe_ext = ext.lower() if ext.lower() in (".mp4", ".mkv", ".webm") else ".mp4"
    safe_name = safe_stem + safe_ext
    local_file = f"/tmp/{safe_name}"
    if os.path.exists(local_file):
        os.remove(local_file)

    ok = False
    err_detail = ""
    print(f"[queue] Processing {safe_name} from {src.split(':', 1)[0]}")
    if src.startswith("tgmsg:"):
        if not API_ID or not API_HASH:
            err_detail = "TG_API_ID or TG_API_HASH secret missing in GitHub"
        else:
            try:
                _, c_str, m_str = src.split(":")
                ok, err_detail = asyncio.run(asyncio.wait_for(
                    download_tg_msg(int(c_str), int(m_str), local_file), timeout=480
                ))
            except Exception as e:
                err_detail = str(e)
    elif src.startswith("http"):
        # yt-dlp is installed once by the workflow, not for every queued item.
        cmd = ["yt-dlp", "--no-warnings", "--retries", "3", "--fragment-retries", "3",
               "--concurrent-fragments", "4", "-f", "best[height<=720][ext=mp4]/best[height<=720]",
               "--no-playlist", "-o", local_file, src]
        if YT_COOKIES:
            cmd[1:1] = ["--cookies", "/tmp/cookies.txt"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=480)
            ok = os.path.exists(local_file) and os.path.getsize(local_file) > 500000
            if not ok:
                err_detail = (res.stderr or "Download did not produce a usable video")[-180:].strip()
        except subprocess.TimeoutExpired:
            err_detail = "Source download exceeded the 8-minute safety limit; item remains queued."

    if ok:
        fsize_mb = round(os.path.getsize(local_file) / (1024**2), 1)
        remote_state = {}
        for remote in ("mega", "pcloud"):
            stats = get_cloud_stats(remote)
            if stats is not None:
                remote_state[remote] = stats

        required_gb = os.path.getsize(local_file) / 1_000_000_000 + 0.25
        candidates = [
            remote for remote, (_, free, total) in remote_state.items()
            if total > 0 and free >= required_gb
        ]
        if not candidates:
            notify(f"❌ No usable MEGA/pCloud destination for {safe_name}. Source retained in queue for retry.")
            continue

        target = random.choice(candidates)
        upload_result = None
        for destination in [target] + [r for r in candidates if r != target]:
            print(f"[storage] Uploading {safe_name} to {destination}; source size {fsize_mb} MB.")
            attempt = subprocess.run(
                ["rclone", "copyto", local_file, f"{destination}:GTA_Clips/{safe_name}",
                 "--retries", "2", "--low-level-retries", "3", "--stats", "15s"],
                capture_output=True, text=True, timeout=600
            )
            if attempt.returncode == 0 and verify_uploaded_file(
                destination, safe_name, os.path.getsize(local_file)
            ):
                target = destination
                upload_result = attempt
                break
            detail = (attempt.stderr or attempt.stdout or "remote size verification failed").strip()
            print(f"[{destination}] upload failed or did not verify: {detail[-350:]}")

        if upload_result is None:
            notify(f"❌ Cloud upload failed or could not be verified for {safe_name}. Source retained in queue for retry.")
            continue

        processed.add(line)
        os.remove(local_file)
        m_stats = get_cloud_stats("mega")
        p_stats = get_cloud_stats("pcloud")
        m_cnt, p_cnt = count_clips("mega"), count_clips("pcloud")
        def quota_line(name, stats, count):
            if stats is None:
                return f"• {name} ({count} visible clips): quota unavailable — check rclone remote/auth"
            used, free, total = stats
            return f"• {name} ({count} visible clips): {used} GB used | {free} GB free (of {total} GB)"
        known = [x for x in (m_stats, p_stats) if x is not None]
        combined = (f"\n🔋 Combined known free: {sum(x[1] for x in known):.2f} GB / {sum(x[2] for x in known):.2f} GB"
                    if known else "\n🔋 Combined quota unavailable; no made-up totals shown.")
        notify(
            f"✅ Upload verified!\n"
            f"📁 File: {safe_name} ({fsize_mb} MB)\n"
            f"☁️ Saved To: {target.upper()}\n\n"
            f"📊 Cloud Storage:\n"
            + quota_line("MEGA", m_stats, m_cnt) + "\n"
            + quota_line("pCloud", p_stats, p_cnt) + combined
        )
    else:
        notify(f"⚠️ Failed to transfer {safe_name}:\nReason: {err_detail}")

# Remove only processed lines so new lines queued mid-run are preserved
if os.path.exists("links.txt"):
    latest = [l.strip() for l in open("links.txt") if l.strip()]
    remaining = [l for l in latest if l not in processed]
    open("links.txt", "w").write(("\n".join(remaining) + "\n") if remaining else "")
