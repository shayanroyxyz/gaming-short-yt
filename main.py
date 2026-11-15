import os, re, time, random, asyncio, textwrap, subprocess, datetime, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from analyzer import analyze_channel_algorithm

SUBREDDITS = {
    "GTA 6": ["GTA6"],
    "GTA 5": ["GTAV", "gtaonline"],
    "GTA San Andreas": ["sanandreas", "GTA"],
    "GTA 4": ["GTAIV", "GTA"],
    "GTA 3": ["GTA3", "GTA"]
}

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

def fetch_social_gta_clip(idx, game_name):
    out_raw = f"raw_{idx}.mp4"
    out_src = f"src_{idx}.mp4"
    for f in [out_raw, out_src]:
        if os.path.exists(f):
            os.remove(f)

    headers = {"User-Agent": "android:com.shayan.gtashorts:v2.0 (by /u/gtaclipcurator)"}
    subs = SUBREDDITS.get(game_name, ["GTA6", "GTA"]) + ["GTA6", "GTA", "GTAV"]
    candidates = []

    for sub in dict.fromkeys(subs):
        for sort_mode in ["hot", "top"]:
            url = f"https://old.reddit.com/r/{sub}/{sort_mode}.json?t=month&limit=40"
            try:
                r = requests.get(url, headers=headers, timeout=12)
                if r.status_code != 200:
                    continue
                posts = r.json().get("data", {}).get("children", [])
                for p in posts:
                    d = p.get("data", {})
                    if d.get("is_video") and not d.get("over_18"):
                        rv = (d.get("media") or {}).get("reddit_video") or {}
                        fb_url = rv.get("fallback_url")
                        dur = float(rv.get("duration") or 0)
                        height = int(rv.get("height") or 0)
                        if fb_url and 8 <= dur <= 120 and height >= 360:
                            candidates.append((d.get("permalink", ""), fb_url, dur, height, d.get("title", "")))
            except Exception as e:
                print(f"Subreddit {sub} fetch skip: {e}")
        if len(candidates) >= 8:
            break

    if not candidates:
        raise RuntimeError(f"No >=360p GTA clips found for {game_name}")

    random.shuffle(candidates)
    downloaded = False
    for permalink, fb_url, dur, height, post_title in candidates:
        print(f"[Video {idx}] Downloading {height}p clip: {post_title[:55]}")
        # Use yt-dlp on permalink first (gets clean 480p/720p stream), fallback to direct fallback_url
        res = subprocess.run([
            "yt-dlp", "--no-warnings", "--socket-timeout", "15",
            "--user-agent", headers["User-Agent"],
            "-f", "bv*[height>=360][height<=720]/bv*[height>=360]/b",
            "-o", out_src, f"https://www.reddit.com{permalink}"
        ], timeout=35)
        if res.returncode != 0 or not os.path.exists(out_src):
            subprocess.run(["curl", "-m", "25", "-L", "-f", "-s", "-A", headers["User-Agent"], fb_url, "-o", out_src])
        if os.path.exists(out_src) and os.path.getsize(out_src) > 250_000:
            downloaded = True
            break

    if not downloaded:
        raise RuntimeError(f"Download failed for video {idx}")

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_src
    ]).decode().strip()
    dur = float(probe)
    start_sec = 0 if dur <= 12 else random.randint(1, max(2, int(dur) - 11))
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", "10",
        "-i", out_src, "-c:v", "libx264", "-preset", "ultrafast", "-an", out_raw
    ], check=True)
    return out_raw

def clean_ascii(text):
    return re.sub(r"[^A-Za-z0-9 .,!?-]", "", text).strip()

def generate_ai_script(game_name, topic_desc, algo_report):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        f"You are optimizing a USA-targeted YouTube Shorts channel. Recent stats:\n{algo_report}\n\n"
        f"Create a high-retention 10-second Short for {game_name} ({topic_desc}).\n"
        "Output exactly 3 plain-text lines (NO emojis, NO quotes, NO markdown):\n"
        f"Line 1: Curiosity YouTube Short title under 72 chars about {game_name} ending with #shorts #gta\n"
        "Line 2: Punchy 2-sentence American gaming commentary (18-24 words total) that loops smoothly.\n"
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
    wrapped = "\n".join(textwrap.wrap(clean_ascii(hook_caption), width=15))
    open(cap_file, "w").write(wrapped)

    # Bold yellow/black caption cleanly positioned at bottom safe zone (y=1380, above Shorts title UI)
    vf = (
        f"[0:v]setpts=0.96*PTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"eq=contrast=1.14:saturation=1.20,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={cap_file}:"
        f"fontcolor=yellow:borderw=7:bordercolor=black:fontsize=74:line_spacing=14:x=(w-text_w)/2:y=1380[v]"
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
    algo = analyze_channel_algorithm()
    top_games = algo["best_games"][:2]
    base_delay = 0 if algo["hours_since_last"] >= 3.0 else int((3.0 - algo["hours_since_last"]) * 60) + 5

    for i, game_name in enumerate(top_games, start=1):
        topic_desc = TOPIC_MAP.get(game_name, "hidden secrets and crazy physics in GTA")
        raw_mp4 = fetch_social_gta_clip(i, game_name)
        title, voice_text, hook_caption = generate_ai_script(game_name, topic_desc, algo["report"])
        voice_mp3 = f"voice_{i}.mp3"
        asyncio.run(make_voice(voice_text, voice_mp3))
        final_mp4 = render_short(i, raw_mp4, voice_mp3, hook_caption)
        delay = base_delay if i == 1 else base_delay + 12
        upload_video(final_mp4, title, f"{voice_text}\n\n#shorts #gta #gaming", delay_minutes=delay)
