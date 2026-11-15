import os, re, time, random, asyncio, textwrap, subprocess, datetime, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from analyzer import analyze_channel_algorithm

TOPIC_MAP = {
    "GTA San Andreas": "crazy hidden details and AI secrets in GTA San Andreas",
    "GTA 6": "mind-blowing Vice City NPC density and beach physics in GTA 6",
    "GTA 5": "insane hidden secrets in GTA 5 that took years to find",
    "GTA 4": "why GTA 4 Euphoria ragdoll and car physics still beat modern games",
    "GTA 3": "secret Liberty City mechanics in GTA 3"
}

def validate_env():
    required = ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub Secrets: {missing}")

def setup_cookies():
    ck = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if ck:
        open("cookies.txt", "w").write(ck)
        return "cookies.txt"
    return None

def fetch_hd_gta_clip(idx, game_name, cookie_file):
    out_raw = f"raw_{idx}.mp4"
    out_src = f"src_{idx}.mp4"
    for f in [out_raw, out_src]:
        if os.path.exists(f):
            os.remove(f)

    candidates = []
    # 1. Load any custom X (Twitter) / Dailymotion URLs from sources.txt
    if os.path.exists("sources.txt"):
        file_urls = [l.strip() for l in open("sources.txt") if l.strip() and not l.startswith("#")]
        random.shuffle(file_urls)
        candidates.extend(file_urls)

    # 2. If burner YouTube cookies exist, search crisp 1080p/720p gameplay directly on YouTube
    if cookie_file:
        candidates.append(f"ytsearch8:{game_name} 4k 60fps gameplay no commentary")

    # 3. Public Dailymotion HD search (works with zero accounts on GitHub Actions)
    dm_q = requests.utils.quote(f"{game_name} gameplay")
    candidates.append(f"https://www.dailymotion.com/search/{dm_q}/videos")

    downloaded = False
    for target in candidates:
        cmd = [
            "yt-dlp", "--no-warnings", "--socket-timeout", "15",
            "--match-title", "(?i)(gta|grand theft auto|vice city|san andreas)",
            "--reject-title", "(?i)(review|reaction|podcast|explained|episode)",
            "--match-filter", "duration > 20 & duration < 900",
            "--playlist-items", "1-6",
            "--max-downloads", "1",
            "-f", "bv*[height>=720][ext=mp4]+ba[ext=m4a]/b[height>=720][ext=mp4]/bv*[height>=720]/b",
            "--merge-output-format", "mp4",
            "-o", out_src,
            target
        ]
        if cookie_file and ("ytsearch" in target or "youtu" in target):
            cmd.extend(["--cookies", cookie_file])

        print(f"[Video {idx}] Fetching HD source:", target)
        subprocess.run(cmd, timeout=60)
        if os.path.exists(out_src) and os.path.getsize(out_src) > 1_000_000:
            downloaded = True
            break

    if not downloaded:
        raise RuntimeError(f"No HD 720p+ clip downloaded for {game_name}. Add X/Twitter clip URLs to sources.txt or set YOUTUBE_COOKIES.")

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_src
    ]).decode().strip()
    dur = float(probe)
    mid_start = max(3, int(dur * 0.25))
    mid_end = max(mid_start + 1, int(dur * 0.75) - 11)
    start_sec = random.randint(mid_start, mid_end)

    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", "10",
        "-i", out_src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-an", out_raw
    ], check=True)
    return out_raw

def clean_ascii(text):
    return re.sub(r"[^A-Za-z0-9 .,!?-]", "", text).strip()

def generate_ai_script(game_name, topic_desc, algo_report):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        f"You are optimizing a YouTube Shorts channel. Recent channel performance:\n{algo_report}\n\n"
        f"Create a high-retention 10-second Short for {game_name} ({topic_desc}).\n"
        "Output exactly 3 plain-text lines (NO emojis, NO quotes, NO markdown):\n"
        f"Line 1: Curiosity YouTube Short title under 72 chars about {game_name} ending with #shorts #gta\n"
        "Line 2: Fast, punchy 2-sentence gaming voiceover (18-24 words total) that loops smoothly.\n"
        "Line 3: Bold 3-4 word hook caption in ALL CAPS."
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
        f"Look closely at what happens right here in {game_name}... Rockstar hid insane details nobody ever spots.",
        f"{game_name.upper()} SECRET DETAIL"
    )

async def make_voice(text, out_mp3):
    comm = edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural", rate="+10%", pitch="-2Hz")
    await comm.save(out_mp3)

def render_short(idx, raw_mp4, voice_mp3, hook_caption):
    cap_file = f"cap_{idx}.txt"
    final_mp4 = f"final_{idx}.mp4"
    wrapped = "\n".join(textwrap.wrap(clean_ascii(hook_caption), width=18))
    open(cap_file, "w").write(wrapped)

    # Crisp 1080x1920 Lanczos upscale + unsharp + bold bottom-safe caption at y=1420
    vf = (
        f"[0:v]setpts=0.96*PTS,scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"unsharp=5:5:0.8:5:5:0.0,eq=contrast=1.12:saturation=1.16,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={cap_file}:"
        f"fontcolor=yellow:borderw=7:bordercolor=black:box=1:boxcolor=black@0.55:boxborderw=14:"
        f"fontsize=66:line_spacing=12:x=(w-text_w)/2:y=1420[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_mp4, "-i", voice_mp3,
        "-filter_complex", vf,
        "-map", "[v]", "-map", "1:a", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "160k", final_mp4
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
                "tags": ["GTA", "GTASanAndreas", "GTA6", "GTA5", "GTA4", "RockstarGames", "Shorts"],
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
    cookie_file = setup_cookies()
    algo = analyze_channel_algorithm()
    top_games = algo["best_games"][:2]
    base_delay = 0 if algo["hours_since_last"] >= 3.0 else int((3.0 - algo["hours_since_last"]) * 60) + 5

    for i, game_name in enumerate(top_games, start=1):
        topic_desc = TOPIC_MAP.get(game_name, "hidden secrets and crazy physics in GTA")
        raw_mp4 = fetch_hd_gta_clip(i, game_name, cookie_file)
        title, voice_text, hook_caption = generate_ai_script(game_name, topic_desc, algo["report"])
        voice_mp3 = f"voice_{i}.mp3"
        asyncio.run(make_voice(voice_text, voice_mp3))
        final_mp4 = render_short(i, raw_mp4, voice_mp3, hook_caption)
        delay = base_delay if i == 1 else base_delay + 12
        upload_video(final_mp4, title, f"{voice_text}\n\n#shorts #gta #gaming", delay_minutes=delay)
