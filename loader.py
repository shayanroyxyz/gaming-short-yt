"""Cloud ingestion using Telegram MTProto and randomized single-cloud storage.

Queue format: <source> | <filename>[ | retries=N]
Sources: tgmsg:<chat_id>:<message_id> or an HTTP(S) URL.
"""
import json
import os
import random
import re
import subprocess
from pathlib import Path

import requests
from telethon.sync import TelegramClient

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API_ID = os.environ.get("TG_API_ID", "").strip()
API_HASH = os.environ.get("TG_API_HASH", "").strip()
RCLONE_CONF = os.environ.get("RCLONE_CONF", "").strip()
YT_COOKIES = os.environ.get("YT_COOKIES", "").strip()
QUEUE = Path("links.txt")
MAX_RETRIES = 3  # retries after the initial attempt
MIN_VIDEO_BYTES = 100_000
CLOUDS = ("mega", "pcloud")
SESSION = requests.Session()


def notify(message):
    if not TOKEN or not CHAT_ID:
        return
    try:
        SESSION.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message[:4000]},
            timeout=20,
        ).raise_for_status()
    except requests.RequestException as exc:
        print(f"Telegram notification failed: {exc}")


def run(command, *, check=True, capture=False):
    return subprocess.run(
        command, check=check, text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def safe_filename(value):
    name = re.sub(r"[^a-zA-Z0-9_.()\[\]-]", "_", Path(value.strip()).name)
    name = name.strip("._")
    if not name:
        raise ValueError("A non-empty filename is required")
    if not Path(name).suffix:
        name += ".mp4"
    return name[:180]


def parse_queue_line(line):
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 2:
        raise ValueError("Expected source | filename")
    source, filename = parts[0], safe_filename(parts[1])
    retries = 0
    for part in parts[2:]:
        match = re.fullmatch(r"retries\s*=\s*(\d+)", part, re.IGNORECASE)
        if match:
            retries = int(match.group(1))
    return source, filename, retries


def download_telegram_message(source, destination):
    if not (TOKEN and API_ID and API_HASH):
        raise RuntimeError("TELEGRAM_BOT_TOKEN, TG_API_ID and TG_API_HASH are required for MTProto downloads")
    match = re.fullmatch(r"tgmsg:(-?\d+):(\d+)", source)
    if not match:
        raise ValueError("Invalid Telegram source; expected tgmsg:<chat_id>:<message_id>")
    chat_id, message_id = int(match.group(1)), int(match.group(2))

    # A fresh ephemeral bot session is created on the runner; no phone storage or
    # persistent user-account session is required. MTProto supports large media.
    client = TelegramClient("telegram_ingest_bot", int(API_ID), API_HASH)
    try:
        client.start(bot_token=TOKEN)
        # Populate Telethon's entity/access-hash cache for the private owner chat.
        client.get_dialogs(limit=500)
        peer = client.get_input_entity(chat_id)
        message = client.get_messages(peer, ids=message_id)
        if not message or not message.media:
            raise RuntimeError(f"Telegram message {message_id} in chat {chat_id} has no downloadable media")
        downloaded = client.download_media(message, file=str(destination))
        if not downloaded:
            raise RuntimeError("Telethon did not return a downloaded media path")
    finally:
        client.disconnect()

    if not destination.is_file() or destination.stat().st_size < MIN_VIDEO_BYTES:
        raise RuntimeError("Telegram MTProto download is empty or too small")
    return destination.stat().st_size


def download_youtube(url, destination):
    command = [
        "yt-dlp", "--no-playlist", "--no-progress",
        "-f", "best[height<=720][ext=mp4]/best[height<=720]/best",
        "-o", str(destination),
    ]
    if YT_COOKIES:
        cookie_file = Path("/tmp/yt-cookies.txt")
        cookie_file.write_text(YT_COOKIES, encoding="utf-8")
        command[1:1] = ["--cookies", str(cookie_file)]
    command.append(url)
    run(command)
    if not destination.is_file() or destination.stat().st_size < MIN_VIDEO_BYTES:
        raise RuntimeError("yt-dlp did not produce a valid video file")
    return destination.stat().st_size


def cloud_listing(remote):
    result = run(["rclone", "lsf", "--files-only", f"{remote}:GTA_Clips"], check=False, capture=True)
    if result.returncode != 0:
        # An empty, not-yet-created folder is acceptable; an unavailable remote is not.
        probe = run(["rclone", "about", "--json", f"{remote}:"], check=False, capture=True)
        if probe.returncode != 0:
            raise RuntimeError(f"Cannot access {remote}: {result.stderr[-300:]}")
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def cloud_space(remote):
    result = run(["rclone", "about", "--json", f"{remote}:"], check=False, capture=True)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        total = int(data.get("total") or 0)
        free = int(data.get("free") or 0)
        used = int(data.get("used") if data.get("used") is not None else max(0, total - free))
        return {"total": total, "free": free, "used": used}
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def format_gb(value):
    return f"{value / (1024 ** 3):.2f} GB" if value is not None else "unknown"


def choose_cloud(file_size):
    spaces = {remote: cloud_space(remote) for remote in CLOUDS}
    eligible = [
        remote for remote, space in spaces.items()
        if space is None or space["free"] >= file_size
    ]
    if not eligible:
        raise RuntimeError("Neither cloud reports enough free space for this file")
    # Randomized weighted choice: more free capacity gives a proportionally
    # higher chance, while both eligible clouds remain selectable.
    weights = [max(1, spaces[r]["free"]) if spaces[r] else 1 for r in eligible]
    return random.choices(eligible, weights=weights, k=1)[0], spaces


def upload_single_cloud(local_path, filename, file_size):
    listings = {remote: cloud_listing(remote) for remote in CLOUDS}
    existing = [remote for remote, names in listings.items() if filename in names]
    if existing:
        return None, f"Skipped duplicate filename (already on {', '.join(existing)})"

    first, _ = choose_cloud(file_size)
    order = [first] + [remote for remote in CLOUDS if remote != first]
    errors = []
    for remote in order:
        target = f"{remote}:GTA_Clips/{filename}"
        upload = run(["rclone", "copyto", str(local_path), target], check=False, capture=True)
        if upload.returncode != 0:
            errors.append(f"{remote}: {(upload.stderr or 'upload failed')[-300:]}")
            continue
        verify = run(["rclone", "check", str(local_path), target, "--one-way"], check=False, capture=True)
        if verify.returncode == 0:
            return remote, "Uploaded and checksum-verified"
        errors.append(f"{remote}: checksum verification failed")
        # A failed partial upload must not block failover under the same filename.
        run(["rclone", "deletefile", target], check=False)
    raise RuntimeError("Both cloud uploads failed: " + "; ".join(errors))


def storage_report(saved_cloud, filename, file_size, status):
    counts, spaces = {}, {}
    for remote in CLOUDS:
        try:
            counts[remote] = len(cloud_listing(remote))
        except Exception:
            counts[remote] = "unavailable"
        spaces[remote] = cloud_space(remote)
    lines = [
        f"{'✅' if saved_cloud else 'ℹ️'} Unique Upload Complete!" if saved_cloud else "ℹ️ Duplicate Skipped",
        f"File: {filename}",
        f"Size: {format_gb(file_size)} ({file_size:,} bytes)",
        f"Saved to: {saved_cloud or 'already existed'}",
        f"MEGA videos: {counts['mega']} | pCloud videos: {counts['pcloud']}",
    ]
    for remote in CLOUDS:
        space = spaces[remote]
        if space:
            lines.append(
                f"{remote.upper()}: used {format_gb(space['used'])} / left {format_gb(space['free'])}"
            )
        else:
            lines.append(f"{remote.upper()}: used unknown / left unknown (rclone about unavailable)")
    lines.append(status)
    notify("\n".join(lines))


def main():
    if not QUEUE.exists():
        return
    pending = [line.strip() for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not pending:
        return
    if not RCLONE_CONF:
        raise RuntimeError("RCLONE_CONF is not configured")

    config_dir = Path.home() / ".config" / "rclone"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "rclone.conf").write_text(RCLONE_CONF, encoding="utf-8")

    failed = []
    succeeded = 0
    for line in pending:
        try:
            source, filename, retries = parse_queue_line(line)
        except Exception as exc:
            notify(f"⚠️ Invalid queue entry removed for manual review:\n{line[:250]}\n{exc}")
            continue


        local_path = Path("/tmp") / f"ingest_{os.getpid()}_{filename}"
        try:
            if local_path.exists():
                local_path.unlink()
            if source.startswith("tgmsg:"):
                file_size = download_telegram_message(source, local_path)
            elif source.startswith(("https://", "http://")):
                file_size = download_youtube(source, local_path)
            elif source.startswith("tgfile:"):
                # Compatibility for queue entries created by the previous bot version.
                # Telegram hosted Bot API downloads remain limited to 20 MB.
                file_id = source.split(":", 1)[1].strip()
                response = SESSION.get(
                    f"https://api.telegram.org/bot{TOKEN}/getFile",
                    params={"file_id": file_id}, timeout=45
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    raise RuntimeError(f"Legacy Telegram getFile failed: {payload.get('description', 'unknown error')}")
                file_path = payload["result"]["file_path"]
                with SESSION.get(
                    f"https://api.telegram.org/file/bot{TOKEN}/{file_path}",
                    stream=True, timeout=(30, 300)
                ) as stream:
                    stream.raise_for_status()
                    with open(local_path, "wb") as output:
                        for chunk in stream.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                output.write(chunk)
                file_size = local_path.stat().st_size
                if file_size < MIN_VIDEO_BYTES:
                    raise RuntimeError("Legacy Telegram download was empty or too small")
            else:
                raise ValueError("Unsupported source; use tgmsg:<chat_id>:<message_id> or an HTTP(S) URL")

            saved_cloud, status = upload_single_cloud(local_path, filename, file_size)
            if saved_cloud:
                succeeded += 1
            storage_report(saved_cloud, filename, file_size, status)
        except Exception as exc:
            next_retry = retries + 1
            if next_retry <= MAX_RETRIES:
                failed.append(f"{source} | {filename} | retries={next_retry}")
                notify(
                    f"⚠️ Transfer failed (retry {next_retry}/{MAX_RETRIES}); retained in queue:\n"
                    f"{filename}\n{str(exc)[:650]}"
                )
            else:
                notify(f"⛔ Transfer failed after {MAX_RETRIES} attempts; removed from queue:\n{filename}\n{str(exc)[:650]}")
        finally:
            if local_path.exists():
                local_path.unlink()

    # Retain only retryable failures. Workflow persists this queue back to GitHub.
    QUEUE.write_text("".join(f"{item}\n" for item in failed), encoding="utf-8")
    print(f"Ingestion summary: {succeeded} uploaded, {len(failed)} retryable")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        notify(f"🚨 Loader stopped safely: {exc}")
        raise
