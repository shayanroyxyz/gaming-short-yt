"""Reliable link/video ingestion to MEGA and pCloud.

Queue format: <youtube-url-or-tgfile:file_id> | <filename>
Failed items remain in links.txt for a later retry. A queue item is removed only
after both cloud destinations have been verified.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
RCLONE_CONF = os.environ.get("RCLONE_CONF", "").strip()
YT_COOKIES = os.environ.get("YT_COOKIES", "").strip()
TG_API = os.environ.get("TG_API_BASE", "https://api.telegram.org").rstrip("/")
QUEUE = Path("links.txt")
MIN_VIDEO_BYTES = 100_000
SESSION = requests.Session()


def notify(message):
    if not TOKEN or not CHAT_ID:
        return
    try:
        SESSION.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message[:4000]},
            timeout=15,
        )
    except requests.RequestException:
        pass


def run(command, *, check=True, capture=False):
    return subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def safe_filename(value):
    name = re.sub(r"[^a-zA-Z0-9_.()\[\]-]", "_", value.strip())
    name = name.strip("._")
    if not name:
        raise ValueError("A non-empty filename is required")
    if not Path(name).suffix:
        name += ".mp4"
    return name[:180]


def download_telegram_file(file_id, destination):
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    response = SESSION.get(
        f"{TG_API}/bot{TOKEN}/getFile",
        params={"file_id": file_id},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram getFile failed: {payload.get('description', 'unknown error')}")

    file_path = (payload.get("result") or {}).get("file_path")
    if not file_path:
        raise RuntimeError("Telegram did not return a file_path")

    # Local Bot API servers may return an absolute path on the runner/container.
    if os.path.isabs(file_path) and os.path.isfile(file_path):
        shutil.copy2(file_path, destination)
    else:
        url = f"{TG_API}/file/bot{TOKEN}/{file_path.lstrip('/')}"
        with SESSION.get(url, stream=True, timeout=(30, 600)) as stream:
            stream.raise_for_status()
            with open(destination, "wb") as output:
                for chunk in stream.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)

    if not destination.is_file() or destination.stat().st_size < MIN_VIDEO_BYTES:
        raise RuntimeError("Telegram download is empty or too small to be a valid video")


def download_youtube(url, destination):
    command = [
        "yt-dlp",
        "--no-playlist",
        "--no-progress",
        "-f", "best[height<=720][ext=mp4]/best[height<=720]/best",
        "-o", str(destination),
    ]
    if YT_COOKIES:
        cookie_file = Path("/tmp/yt-cookies.txt")
        cookie_file.write_text(YT_COOKIES)
        command[1:1] = ["--cookies", str(cookie_file)]
    command.append(url)
    run(command)
    if not destination.is_file() or destination.stat().st_size < MIN_VIDEO_BYTES:
        raise RuntimeError("yt-dlp did not produce a valid video file")


def remote_file_exists(remote_path):
    result = run(["rclone", "lsjson", remote_path], check=False, capture=True)
    return result.returncode == 0 and bool(result.stdout.strip())


def transfer_to_both_clouds(local_path, filename):
    destinations = [
        f"mega:GTA_Clips/{filename}",
        f"pcloud:GTA_Clips/{filename}",
    ]
    failures = []
    for target in destinations:
        # --ignore-existing makes retries safe when the first cloud succeeded
        # but the second cloud failed on the previous attempt.
        result = run(
            ["rclone", "copyto", "--ignore-existing", str(local_path), target],
            check=False,
            capture=True,
        )
        if result.returncode != 0 and not remote_file_exists(target):
            detail = (result.stderr or "rclone failed").strip()[-500:]
            failures.append(f"{target}: {detail}")
            continue
        if not remote_file_exists(target):
            failures.append(f"{target}: destination could not be verified")
    if failures:
        raise RuntimeError("; ".join(failures))


def main():
    if not QUEUE.exists():
        return
    lines = QUEUE.read_text(encoding="utf-8").splitlines()
    pending = [line.strip() for line in lines if line.strip()]
    if not pending:
        return
    if not RCLONE_CONF:
        raise RuntimeError("RCLONE_CONF is not configured")

    config_dir = Path.home() / ".config" / "rclone"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "rclone.conf").write_text(RCLONE_CONF)

    failed = []
    succeeded = []
    for line in pending:
        if "|" not in line:
            failed.append(line)
            notify(f"⚠️ Invalid queue entry kept for review: {line[:200]}")
            continue

        source, raw_name = (part.strip() for part in line.split("|", 1))
        local_path = Path("/tmp") / safe_filename(raw_name)
        try:
            if local_path.exists():
                local_path.unlink()
            if source.startswith("tgfile:"):
                download_telegram_file(source.split(":", 1)[1].strip(), local_path)
            elif source.startswith(("https://", "http://")):
                download_youtube(source, local_path)
            else:
                raise ValueError("Unsupported source; expected an HTTP(S) URL or tgfile:file_id")

            transfer_to_both_clouds(local_path, local_path.name)
            succeeded.append(local_path.name)
            notify(f"✅ Verified in MEGA and pCloud:\n📁 {local_path.name}")
        except Exception as error:
            failed.append(line)
            notify(f"⚠️ Transfer failed; item kept in queue for retry:\n{raw_name}\n{str(error)[:700]}")
        finally:
            if local_path.exists():
                local_path.unlink()

    # Preserve failures and any malformed entries. Do not silently empty queue.
    QUEUE.write_text("".join(f"{item}\n" for item in failed), encoding="utf-8")
    print(f"Transfer summary: {len(succeeded)} succeeded, {len(failed)} retained for retry")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        notify(f"🚨 Loader stopped safely: {exc}")
        raise
