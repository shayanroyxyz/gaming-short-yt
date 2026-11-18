import os, re, json, random, asyncio, datetime, subprocess, xml.etree.ElementTree as ET, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

def validate_env():
    required = ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub Secrets: {missing}")

def pick_game_theme():
    gta_pool = [
        ("GTA 6", ["GTA6", "GrandTheftAutoV", "GTA"], "insane hidden details and realism in GTA 6"),
        ("GTA 5", ["GrandTheftAutoV", "gtaonline", "GTA"], "secret physics details and hidden stories in GTA 5"),
        ("GTA San Andreas", ["GTA", "sanandreas", "gaming"], "legendary mysteries and hidden facts in GTA San Andreas"),
        ("GTA 4", ["GTA", "GTAIV", "gaming"], "why GTA 4 physics and dark story details were ahead of their time")
    ]
    other_pool = [
        ("Minecraft", ["Minecraft", "gaming"], "insane secret mechanics and rare moments in Minecraft"),
        ("Roblox", ["roblox", "gaming"], "crazy viral moments and hidden secrets in Roblox")
    ]
    if datetime.date.today() <= datetime.date(2026, 12, 18):
        return random.choice(gta_pool) if random.random() < 0.85 else random.choice(other_pool)
    return random.choice(gta_pool + other_pool)

def fetch_best_available_clip(game_name, subreddits):
    random.shuffle(subreddits)
    headers = {"User-Agent": UA}
    candidate_urls = []

    # 1. Reddit Public RSS Feeds (unblocked XML endpoint)
    for sub in subreddits:
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot/.rss?limit=35", headers=headers, timeout=15)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                    link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                    if link_el is not None and link_el.attrib.get("href"):
                        candidate_urls.append(link_el.attrib["href"])
        except Exception as e:
            print("RSS skip:", sub, e)

    random.shuffle(candidate_urls)
    for url in candidate_urls[:20]:
        print("Trying Reddit RSS post (no quality barrier):", url)
        if os.path.exists("full_source.mp4"):
            os.remove("full_source.mp4")
        res = subprocess.run([
            "yt-dlp", "--user-agent", UA,
            "-f", "bv*+ba/b",
            "--merge-output-format", "mp4",
            "-o", "full_source.mp4", url
        ])
        if res.returncode == 0 and os.path.exists("full_source.mp4") and os.path.getsize("full_source.mp4") > 300_000:
            print("Downloaded clip successfully from Reddit RSS!")
            return

    # 2. Backup: YouTube embedded/tv client (no cookies, no quality filter)
    q = f"ytsearch6:{game_name} gameplay moments"
    print("Trying YouTube web_embedded/tv fallback:", q)
    subprocess.run([
        "yt-dlp",
        "--extractor-args", "youtube:player-client=web_embedded,tv",
        "--match-filter", "duration > 15 & duration < 300",
        "--max-downloads", "1",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", "full_source.mp4", q
    ], check=False)

    if os.path.exists("full_source.mp4") and os.path.getsize("full_source.mp4") > 300_000:
        print("Downloaded clip successfully from YouTube fallback!")
        return

    raise RuntimeError("Could not fetch a video clip in this run.")

def slice_best_segment():
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", "full_source.mp4"
    ]).decode().strip()
    dur = float(probe)
    clip_len = min(22.0, max(12.0, dur - 1.0))
    max_start = max(0, int(dur - clip_len))
    start_sec = random.randint(0, max_start) if max_start > 0 else 0
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", str(clip_len),
        "-i", "full_source.mp4", "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-an", "raw.mp4"
    ], check=True)

def generate_us_viral_script(game_name, angle):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        f"You are a viral US gaming YouTube Shorts creator. Game: {game_name}. Topic: {angle}.\n"
        "Write a high-retention script for an American audience.\n"
        "Output ONLY valid JSON with keys: title, script, tags\n"
        "- title: punchy curiosity title under 75 chars ending with #shorts #gta (or #gaming)\n"
        "- script: 35 to 45 words total, 3 short punchy sentences with natural pauses (...) revealing a mind-blowing fact, hidden story, or secret detail.\n"
        "- tags: list of 5 relevant tags without #"
    )
    res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = re.sub(r"^```json|```$", "", res.text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(raw)
    return data["title"][:85], data["script"], data.get("tags", [game_name.replace(" ", ""), "Shorts", "Gaming"])

async def create_voice_and_synced_srt(script):
    communicate = edge_tts.Communicate(script, "en-US-AndrewMultilingualNeural", rate="+7%", pitch="-2Hz")
    await communicate.save("voice.mp3")

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", "voice.mp3"
    ]).decode().strip()
    total_dur = float(probe)

    words = script.split()
    chunks = [" ".join(words[i:i+3]).upper() for i in range(0, len(words), 3)]
    step = total_dur / max(1, len(chunks))

    def fmt_ts(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    srt_lines = []
    for idx, chunk in enumerate(chunks):
        t0 = idx * step
        t1 = (idx + 1) * step
        srt_lines.append(f"{idx+1}\n{fmt_ts(t0)} --> {fmt_ts(t1)}\n{chunk}\n")
    open("subs.srt", "w").write("\n".join(srt_lines))

def render_hd_short():
    vf = (
        "[0:v]setpts=0.98*PTS,scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,unsharp=5:5:0.8:5:5:0.0,eq=contrast=1.08:saturation=1.15,"
        "subtitles=subs.srt:force_style='FontName=DejaVu Sans,FontSize=22,Bold=1,"
        "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=95'[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", "raw.mp4", "-i", "voice.mp3",
        "-filter_complex", vf,
        "-map", "[v]", "-map", "1:a", "-shortest",
        "-c:v", "libx264", "-preset", "fast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "final.mp4"
    ], check=True)

def upload_to_youtube(title, description, tags):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    youtube = build("youtube", "v3", credentials=creds)
    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "20"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        },
        media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    )
    resp = req.execute()
    print("SUCCESS! Published Short ID:", resp.get("id"))

if __name__ == "__main__":
    validate_env()
    game_name, subs, angle = pick_game_theme()
    fetch_best_available_clip(game_name, subs)
    slice_best_segment()
    title, script, tags = generate_us_viral_script(game_name, angle)
    asyncio.run(create_voice_and_synced_srt(script))
    render_hd_short()
    upload_to_youtube(title, f"{script}\n\n#shorts #gta #gaming", tags)
