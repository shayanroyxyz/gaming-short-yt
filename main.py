import os, re, time, random, asyncio, textwrap, subprocess, datetime, xml.etree.ElementTree as ET, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from analyzer import analyze_channel_algorithm

SUBREDDITS = {
    "GTA 6": ["GTA6", "GTA"],
    "GTA 5": ["GTAV", "gtaonline", "GTA"],
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

def setup_cookies():
    ig_path, x_path = None, None
    if os.environ.get("IG_COOKIES", "").strip():
        ig_path = "/tmp/ig_cookies.txt"
        open(ig_path, "w").write(os.environ["IG_COOKIES"])
        os.chmod(ig_path, 0o600)
    if os.environ.get("X_COOKIES", "").strip():
        x_path = "/tmp/x_cookies.txt"
        open(x_path, "w").write(os.environ["X_COOKIES"])
        os.chmod(x_path, 0o600)
    return ig_path, x_path

def validate_env():
    required = ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub Secrets: {missing}")

def valid_video_file(path):
    if not os.path.exists(path) or os.path.getsize(path) < 250_000:
        return False
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path
        ]).decode().strip()
        w, h = map(int, out.split("x"))
        return min(w, h) >= 360
    except Exception:
        return False

def discover_social_urls(game_name):
    urls = []
    if os.path.exists("sources.txt"):
        for line in open("sources.txt"):
            u = line.strip()
            if u.startswith("http") and ("x.com/" in u or "twitter.com/" in u or "instagram.com/" in u):
                urls.append(u)

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for domain in ["x.com", "instagram.com/reel"]:
        rss_q = requests.utils.quote(f"site:{domain} \"{game_name}\" gameplay OR clip")
        try:
            r = requests.get(f"https://news.google.com/rss/search?q={rss_q}&hl=en-US&gl=US&ceid=US:en", headers=headers, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                for item in root.findall(".//item/link")[:6]:
                    if item.text and ("x.com/" in item.text or "instagram.com/" in item.text):
                        urls.append(item.text.strip())
        except Exception:
            pass
    random.shuffle(urls)
    return list(dict.fromkeys(urls))

def fetch_clip(idx, game_name, ig_cookie, x_cookie):
    out_raw = f"raw_{idx}.mp4"
    out_src = f"src_{idx}.mp4"
    for f in [out_raw, out_src]:
        if os.path.exists(f):
            os.remove(f)

    # TIER 1: Paced X / Instagram extraction (with isolated burner cookies)
    for url in discover_social_urls(game_name)[:4]:
        is_ig = "instagram.com" in url
        if is_ig and not ig_cookie:
            continue
        cmd = [
            "yt-dlp", "--no-warnings", "--socket-timeout", "15",
            "--sleep-requests", "5", "--min-sleep-interval", "6", "--max-sleep-interval", "12",
            "-f", "bv*[height>=360][height<=1080]+ba/b[height>=360]/b",
            "--merge-output-format", "mp4", "-o", out_src, url
        ]
        if is_ig and ig_cookie:
            cmd[1:1] = ["--cookies", ig_cookie]
        elif not is_ig and x_cookie:
            cmd[1:1] = ["--cookies", x_cookie]
        print(f"[Video {idx}] Tier 1 Social: {url}")
        try:
            subprocess.run(cmd, timeout=45)
        except Exception:
            pass
        if valid_video_file(out_src):
            break
        if os.path.exists(out_src):
            os.remove(out_src)

    # TIER 2: Dailymotion public gameplay search (unblocked on GitHub Actions, >=360p)
    if not valid_video_file(out_src):
        dm_search = f"https://www.dailymotion.com/search/{requests.utils.quote(game_name + chr(32) + chr(103)+chr(97)+chr(109)+chr(101)+chr(112)+chr(108)+chr(97)+chr(121))}/videos"
        print(f"[Video {idx}] Tier 2 Dailymotion search for {game_name}...")
        try:
            subprocess.run([
                "yt-dlp", "--no-warnings", "--socket-timeout", "15",
                "--playlist-items", f"{random.randint(1, 5)}",
                "--match-title", "(?i)(gta|grand theft auto)",
                "--match-filter", "duration > 15 & duration < 600",
                "--max-downloads", "1",
                "-f", "mp4[height>=360][height<=720]/best[height>=360][height<=720]",
                "-o", out_src, dm_search
            ], timeout=45)
        except Exception:
            pass

    # TIER 3: Reddit JSON fallback
    if not valid_video_file(out_src):
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36"}
        for sub in SUBREDDITS.get(game_name, ["GTA", "GTA6"]):
            try:
                r = requests.get(f"https://www.reddit.com/r/{sub}/top.json?t=all&limit=35", headers=headers, timeout=12)
                if r.status_code != 200:
                    continue
                posts = r.json().get("data", {}).get("children", [])
                random.shuffle(posts)
                for p in posts:
                    d = p.get("data", {})
                    rv = (d.get("media") or {}).get("reddit_video") or {}
                    fb = rv.get("fallback_url")
                    if d.get("is_video") and fb and int(rv.get("height") or 0) >= 360:
                        print(f"[Video {idx}] Tier 3 Reddit: {d.get('title', '')[:45]}")
                        subprocess.run(["curl", "-m", "25", "-L", "-f", "-s", "-A", headers["User-Agent"], fb, "-o", out_src])
                        if valid_video_file(out_src):
                            break
            except Exception:
                pass
            if valid_video_file(out_src):
                break

    # TIER 4: Guaranteed Strict-Title Archive.org GTA fallback (>=360p verified)
    if not valid_video_file(out_src):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        q = requests.utils.quote(f"title:(\"{game_name}\" OR \"Grand Theft Auto\") AND mediatype:movies")
        docs = requests.get(f"https://archive.org/advancedsearch.php?q={q}&fl[]=identifier,title&rows=30&output=json", headers=headers, timeout=15).json().get("response", {}).get("docs", [])
        random.shuffle(docs)
        for doc in docs:
            t = str(doc.get("title", "")).lower()
            if ("gta" not in t and "grand theft auto" not in t) or "review" in t:
                continue
            ident = doc.get("identifier")
            try:
                meta = requests.get(f"https://archive.org/metadata/{ident}", headers=headers, timeout=10).json()
                for f in meta.get("files", []):
                    name = f.get("name", "")
                    size = int(f.get("size", 0) or 0)
                    if name.endswith(".mp4") and 1_500_000 < size < 25_000_000:
                        dl_url = f"https://archive.org/download/{ident}/{requests.utils.quote(name)}"
                        print(f"[Video {idx}] Tier 4 Archive GTA: {doc.get('title', '')[:45]}")
                        subprocess.run(["curl", "-m", "30", "-L", "-f", "-s", "-A", headers["User-Agent"], dl_url, "-o", out_src])
                        if valid_video_file(out_src):
                            break
            except Exception:
                pass
            if valid_video_file(out_src):
                break

    if not valid_video_file(out_src):
        raise RuntimeError(f"All 4 tiers exhausted for {game_name}")

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_src
    ]).decode().strip()
    dur = float(probe)
    mid_start = 0 if dur <= 12 else max(1, int(dur * 0.25))
    mid_end = max(mid_start + 1, int(dur * 0.75) - 11)
    start_sec = 0 if dur <= 12 else random.randint(mid_start, mid_end)
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
    for voice in ["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-BrianNeural"]:
        try:
            comm = edge_tts.Communicate(text, voice, rate="+8%")
            await comm.save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000:
                return
        except Exception as e:
            print(f"edge-tts {voice} failed: {e}")
    try:
        from gtts import gTTS
        gTTS(text=text, lang="en", tld="com").save(out_mp3)
        if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000:
            print("Used gTTS fallback voiceover")
            return
    except Exception as e:
        print(f"gTTS failed: {e}")
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "165", "-w", "/tmp/fb.wav", text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", "/tmp/fb.wav", out_mp3], check=True)

def render_short(idx, raw_mp4, voice_mp3, hook_caption):
    cap_file = f"cap_{idx}.txt"
    final_mp4 = f"final_{idx}.mp4"
    wrapped = "\n".join(textwrap.wrap(clean_ascii(hook_caption), width=15))
    open(cap_file, "w").write(wrapped)

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
    ig_cookie, x_cookie = setup_cookies()
    algo = analyze_channel_algorithm()
    top_games = algo["best_games"][:2]
    base_delay = 0 if algo["hours_since_last"] >= 3.0 else int((3.0 - algo["hours_since_last"]) * 60) + 5

    for i, game_name in enumerate(top_games, start=1):
        topic_desc = TOPIC_MAP.get(game_name, "hidden secrets and crazy physics in GTA")
        raw_mp4 = fetch_clip(i, game_name, ig_cookie, x_cookie)
        title, voice_text, hook_caption = generate_ai_script(game_name, topic_desc, algo["report"])
        voice_mp3 = f"voice_{i}.mp3"
        asyncio.run(make_voice(voice_text, voice_mp3))
        final_mp4 = render_short(i, raw_mp4, voice_mp3, hook_caption)
        delay = base_delay if i == 1 else base_delay + 12
        upload_video(final_mp4, title, f"{voice_text}\n\n#shorts #gta #gaming", delay_minutes=delay)
