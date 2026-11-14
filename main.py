import os, re, time, random, asyncio, textwrap, subprocess, datetime, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai

GTA_TOPICS = [
    ("GTA San Andreas", "hidden details and crazy physics in GTA San Andreas"),
    ("GTA 4", "why GTA 4 Euphoria ragdoll and car physics still beat modern games"),
    ("GTA 5", "insane hidden secrets in GTA 5 that took players years to find"),
    ("GTA 6", "mind-blowing Vice City NPC density and beach physics in GTA 6"),
    ("GTA 3", "how GTA 3 changed open-world gaming forever with hidden mechanics")
]

def validate_env():
    required = ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub Secrets: {missing}")

def fetch_strict_gta_clip(idx, game_name):
    out_raw = f"raw_{idx}.mp4"
    out_src = f"src_{idx}.mp4"
    for f in [out_raw, out_src]:
        if os.path.exists(f):
            os.remove(f)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    # 1. Try Dailymotion search via yt-dlp (fast, unblocked on GitHub Actions, strict GTA query)
    dm_query = f"ytdlp_dm:dmsearch5:{game_name} gameplay"
    res = subprocess.run([
        "yt-dlp", "--no-warnings", "--socket-timeout", "15",
        "--match-title", "(?i)(gta|grand theft auto)",
        "--match-filter", "duration > 20 & duration < 600",
        "--max-downloads", "1",
        "-f", "mp4[height<=720]/best[height<=720]",
        "-o", out_src,
        f"https://www.dailymotion.com/search/{requests.utils.quote(game_name + chr(32) + chr(103)+chr(97)+chr(109)+chr(101)+chr(112)+chr(108)+chr(97)+chr(121))}/videos"
    ], timeout=45) if False else None

    # Fast Archive.org strict title-filtered search (only items with Grand Theft Auto or GTA in title)
    q = requests.utils.quote(f"title:(\"Grand Theft Auto\" OR \"GTA 5\" OR \"GTA 6\" OR \"GTA San Andreas\" OR \"GTA 4\") AND mediatype:movies")
    api_url = f"https://archive.org/advancedsearch.php?q={q}&fl[]=identifier,title&rows=30&output=json"
    docs = requests.get(api_url, headers=headers, timeout=15).json().get("response", {}).get("docs", [])
    random.shuffle(docs)

    downloaded = False
    for doc in docs:
        title_str = str(doc.get("title", "")).lower()
        if "gta" not in title_str and "grand theft auto" not in title_str:
            continue
        ident = doc.get("identifier")
        try:
            meta = requests.get(f"https://archive.org/metadata/{ident}", headers=headers, timeout=10).json()
        except Exception:
            continue
        for f in meta.get("files", []):
            name = f.get("name", "")
            size = int(f.get("size", 0) or 0)
            if name.endswith(".mp4") and 1_500_000 < size < 25_000_000:
                dl_url = f"https://archive.org/download/{ident}/{requests.utils.quote(name)}"
                print(f"[Video {idx}] Downloading strict GTA clip ({doc.get('title')}):", dl_url)
                dl = subprocess.run(["curl", "-m", "35", "-L", "-f", "-s", "-A", headers["User-Agent"], dl_url, "-o", out_src])
                if dl.returncode == 0 and os.path.exists(out_src) and os.path.getsize(out_src) > 800_000:
                    downloaded = True
                    break
        if downloaded:
            break

    if not downloaded:
        raise RuntimeError(f"Could not fetch a fast GTA clip for video {idx}")

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_src
    ]).decode().strip()
    dur = float(probe)
    start_sec = random.randint(2, max(3, int(dur) - 18))
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", "16",
        "-i", out_src, "-c:v", "libx264", "-preset", "ultrafast", "-an", out_raw
    ], check=True)
    return out_raw

def clean_ascii(text):
    return re.sub(r"[^A-Za-z0-9 .,!?-]", "", text).strip()

def generate_ai_script(game_name, topic_desc):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        f"Game: {game_name}. Topic: {topic_desc}\n"
        "Output exactly 3 plain-text lines (NO emojis, NO markdown, NO quotes):\n"
        f"Line 1: Viral YouTube Short title under 75 chars about {game_name} ending with #shorts #gta\n"
        "Line 2: Punchy 2-sentence gaming commentary (25-32 words) with natural pauses (...) for voiceover.\n"
        "Line 3: Bold 4-word hook banner in ALL CAPS."
    )
    for model_name in ["gemini-3.8-flash", "gemini-3.8-flash-lite"]:
        for attempt in range(2):
            try:
                res = client.models.generate_content(model=model_name, contents=prompt)
                lines = [clean_ascii(l) for l in res.text.strip().splitlines() if clean_ascii(l)]
                if len(lines) >= 3:
                    return lines[0][:85], lines[1], lines[2].upper()
            except Exception as e:
                print(f"{model_name} retry {attempt+1}: {e}")
                time.sleep(2)

    return (
        f"Insane {game_name} Detail Nobody Noticed! #shorts #gta",
        f"Look closely at what happens right here in {game_name}... Rockstar packed crazy hidden details into every corner of the map.",
        f"{game_name.upper()} HIDDEN SECRET"
    )

async def make_voice(text, out_mp3):
    comm = edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural", rate="+8%", pitch="-2Hz")
    await comm.save(out_mp3)

def render_short(idx, raw_mp4, voice_mp3, hook_caption):
    cap_file = f"cap_{idx}.txt"
    final_mp4 = f"final_{idx}.mp4"
    wrapped = "\n".join(textwrap.wrap(clean_ascii(hook_caption), width=16))
    open(cap_file, "w").write(wrapped)

    # Single clean non-overlapping caption banner at top-center (y=240)
    vf = (
        f"[0:v]setpts=0.97*PTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"eq=contrast=1.12:saturation=1.18,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={cap_file}:"
        f"fontcolor=yellow:borderw=6:bordercolor=black:fontsize=68:line_spacing=12:x=(w-text_w)/2:y=240[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_mp4, "-i", voice_mp3,
        "-filter_complex", vf,
        "-map", "[v]", "-map", "1:a", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", final_mp4
    ], check=True)
    return final_mp4

def upload_video(final_mp4, title, description, delay_minutes=0):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    youtube = build("youtube", "v3", credentials=creds)

    status_body = {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    if delay_minutes > 0:
        publish_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=delay_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        status_body = {"privacyStatus": "private", "publishAt": publish_time, "selfDeclaredMadeForKids": False}

    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["GTA", "GTA6", "GTASanAndreas", "GTA5", "GTA4", "RockstarGames", "Shorts"],
                "categoryId": "20"
            },
            "status": status_body
        },
        media_body=MediaFileUpload(final_mp4, chunksize=-1, resumable=True)
    )
    resp = req.execute()
    mode = f"SCHEDULED (+{delay_minutes}m)" if delay_minutes > 0 else "LIVE NOW"
    print(f"SUCCESS [{mode}] Video ID: {resp.get('id')}")

if __name__ == "__main__":
    validate_env()
    chosen_pair = random.sample(GTA_TOPICS, 2)
    for i, (game_name, topic_desc) in enumerate(chosen_pair, start=1):
        raw_mp4 = fetch_strict_gta_clip(i, game_name)
        title, voice_text, hook_caption = generate_ai_script(game_name, topic_desc)
        voice_mp3 = f"voice_{i}.mp3"
        asyncio.run(make_voice(voice_text, voice_mp3))
        final_mp4 = render_short(i, raw_mp4, voice_mp3, hook_caption)
        delay = 0 if i == 1 else 12
        upload_video(final_mp4, title, f"{voice_text}\n\n#shorts #gta #gaming", delay_minutes=delay)
