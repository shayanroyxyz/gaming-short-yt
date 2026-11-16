import os, re, json, time, random, asyncio, subprocess, datetime, xml.etree.ElementTree as ET, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from analyzer import analyze_channel_algorithm

# 1. Unlimited FREE X (Twitter) creator accounts scanned via FxTwitter & working 2026 Nitter mirror
X_CREATORS = {
    "GTA 5": ["GTABase", "GTA6Intel", "RockstarGames", "GTAVclips"],
    "Minecraft": ["Minecraft", "MinecraftFacts", "MCPE_News", "Dream"],
    "Roblox": ["Roblox", "RBXNews_", "Blox_News", "Roblox_RTC"]
}

# 2. Paste any free RSS.app / FetchRSS Instagram or TikTok XML feed URLs here
EXTRA_RSS_FEEDS = {
    "GTA 5": [],
    "Minecraft": [],
    "Roblox": []
}

GAMES = [
    {
        "name": "GTA 5",
        "search": "GTA 5 gameplay myths stunts mods",
        "tags": ["GTA5", "GTAMyths", "GTA5Gameplay", "RockstarGames", "Shorts"],
        "fallback_script": {
            "title": "3 Insane GTA 5 Clips You Need To See! #shorts #gta",
            "hook": "Watch these three insane GTA 5 moments that broke game physics.",
            "clips": [
                "First up, look at how the ragdoll physics react when launching off Mount Chiliad at full speed... completely unreal.",
                "Second, watch what happens when NPC traffic glitches out during a five-star police chase in downtown Los Santos.",
                "And third, this stunt pilot threads a jet straight through the tightest tunnel on the map without a scratch."
            ]
        }
    },
    {
        "name": "Minecraft",
        "search": "Minecraft gameplay facts myths clutches",
        "tags": ["Minecraft", "MinecraftFacts", "MinecraftMyths", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "3 Insane Minecraft Moments That Seem Impossible! #shorts",
            "hook": "You will not believe these three rare Minecraft gameplay moments.",
            "clips": [
                "First, watch this frame-perfect water bucket clutch from build height that saves the entire hardcore world.",
                "Second, look at this rare mob interaction where creepers panic and sprint away the second a cat appears.",
                "And third, watch what happens when redstone TNT cannons launch a player thousands of blocks in one tick."
            ]
        }
    },
    {
        "name": "Roblox",
        "search": "Roblox gameplay secrets glitches moments",
        "tags": ["Roblox", "RobloxFacts", "RobloxSecrets", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "3 Secret Roblox Moments Nobody Expected! #shorts #roblox",
            "hook": "Check out these three crazy Roblox clips players just discovered.",
            "clips": [
                "First, look at this hidden secret room tucked underneath the map that almost nobody ever finds.",
                "Second, watch how this physics glitch launches players across the entire server in half a second.",
                "And third, check out this pro shortcut that skips the hardest obstacle stage completely."
            ]
        }
    }
]

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

def clean_ascii(text):
    return re.sub(r"[^A-Za-z0-9 .,!?-]", "", str(text)).strip()

def get_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]).decode().strip()
    return float(out)

def valid_gameplay_video(path):
    if not os.path.exists(path) or os.path.getsize(path) < 350_000:
        return False
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path
        ]).decode().strip()
        w, h = map(int, out.split("x"))
        # Must be >=360p AND at least 11 seconds long so we never stitch tiny static clips
        return min(w, h) >= 360 and get_duration(path) >= 11.0
    except Exception:
        return False

def scan_creator_feeds(game_name):
    post_urls = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # 1. Scan all X creator accounts via working 2026 FxTwitter + nitter.jaydenha.uk RSS feeds
    creators = list(X_CREATORS.get(game_name, []))
    random.shuffle(creators)
    for user in creators:
        for feed_url in [f"https://fxtwitter.com/{user}/feed.xml", f"https://nitter.jaydenha.uk/{user}/rss"]:
            try:
                r = requests.get(feed_url, headers=headers, timeout=8)
                if r.status_code == 200 and "<item>" in r.text:
                    root = ET.fromstring(r.text)
                    for item in root.findall(".//item/link")[:8]:
                        if item.text:
                            u = re.sub(r"https?://(nitter\.[^/]+|fxtwitter\.com)", "https://x.com", item.text.strip())
                            post_urls.append(u)
                    break
            except Exception:
                pass

    # 2. Scan any Instagram / TikTok RSS.app feeds
    for feed_url in EXTRA_RSS_FEEDS.get(game_name, []):
        try:
            r = requests.get(feed_url, headers=headers, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                for item in root.findall(".//item/link")[:10]:
                    if item.text:
                        post_urls.append(item.text.strip())
        except Exception:
            pass

    random.shuffle(post_urls)
    return list(dict.fromkeys(post_urls))

def download_creator_clips(game_cfg, ig_cookie, x_cookie, needed=3):
    pool = []
    g_tag = game_cfg["name"].replace(" ", "_")

    # TIER 1: Extract real videos from scanned creator social feeds (X / Instagram)
    urls = scan_creator_feeds(game_cfg["name"])
    print(f"[{game_cfg['name']}] Found {len(urls)} recent creator posts to scan for video...")
    for idx, url in enumerate(urls[:12], start=1):
        if len(pool) >= needed:
            break
        is_ig = "instagram.com" in url
        if is_ig and not ig_cookie:
            continue
        out_f = f"creator_{g_tag}_{idx}.mp4"
        if os.path.exists(out_f):
            os.remove(out_f)

        cmd = [
            "yt-dlp", "--no-warnings", "--socket-timeout", "12",
            "--sleep-requests", "4", "--min-sleep-interval", "4", "--max-sleep-interval", "8",
            "-f", "bv*[height>=360][height<=1080]+ba/b[height>=360]/b",
            "--merge-output-format", "mp4", "-o", out_f, url
        ]
        if is_ig and ig_cookie:
            cmd[1:1] = ["--cookies", ig_cookie]
        elif not is_ig and x_cookie:
            cmd[1:1] = ["--cookies", x_cookie]

        try:
            subprocess.run(cmd, timeout=35)
        except Exception:
            pass
        if valid_gameplay_video(out_f):
            print(f"  -> Grabbed creator video ({get_duration(out_f):.1f}s): {url}")
            pool.append(out_f)
        elif os.path.exists(out_f):
            os.remove(out_f)

    # TIER 2: Dailymotion Gameplay Search (guarantees 3 full >=360p gameplay clips if social posts were text/images)
    if len(pool) < needed:
        q = requests.utils.quote(game_cfg["search"])
        dm_url = f"https://www.dailymotion.com/search/{q}/videos"
        for idx in range(1, 9):
            if len(pool) >= needed:
                break
            out_f = f"dm_{g_tag}_{idx}.mp4"
            if os.path.exists(out_f):
                os.remove(out_f)
            try:
                subprocess.run([
                    "yt-dlp", "--no-warnings", "--socket-timeout", "15",
                    "--playlist-items", str(idx),
                    "--match-title", f"(?i)({game_cfg['name'].split()[0]}|gameplay|myths|stunt|mod)",
                    "--reject-title", "(?i)(unboxing|review|hand|reaction|irl|trailer reaction)",
                    "--match-filter", "duration > 20 & duration < 900",
                    "--max-downloads", "1",
                    "-f", "mp4[height>=360][height<=720]/best[height>=360][height<=720]",
                    "-o", out_f, dm_url
                ], timeout=40)
            except Exception:
                pass
            if valid_gameplay_video(out_f):
                pool.append(out_f)

    if not pool:
        raise RuntimeError(f"No >=360p videos found for {game_cfg['name']}")
    while len(pool) < needed:
        pool.append(random.choice(pool))
    return pool

def call_llm_json(prompt):
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if ds_key:
        is_or = ds_key.startswith("sk-or-")
        url = "https://openrouter.ai/api/v1/chat/completions" if is_or else "https://api.deepseek.com/chat/completions"
        model = "deepseek/deepseek-chat:free" if is_or else "deepseek-chat"
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
                timeout=25
            )
            if r.status_code == 200:
                raw = r.json()["choices"][0]["message"]["content"]
                m = re.search(r"\{.*\}", raw, re.S)
                if m:
                    return json.loads(m.group(0))
        except Exception as e:
            print(f"DeepSeek fallback to Gemini: {e}")

    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gem_key:
        client = genai.Client(api_key=gem_key)
        for m_name in ["gemini-3.8-flash", "gemini-3.8-flash-lite"]:
            try:
                res = client.models.generate_content(model=m_name, contents=prompt)
                m = re.search(r"\{.*\}", res.text, re.S)
                if m:
                    return json.loads(m.group(0))
            except Exception:
                time.sleep(2)
    return None

def generate_full_script(game_cfg):
    prompt = (
        f"Write a full 40-to-45 second YouTube Short compilation script showcasing 3 viral {game_cfg['name']} clips.\n"
        "Structure MUST have a strong 3-second hook PLUS 3 full main content segments (25-32 words each).\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        f"  \"title\": \"Viral title under 70 chars about 3 insane {game_cfg['name']} clips ending with #shorts\","
        "  \"hook\": \"Fast 1-sentence pattern-interrupt hook (10-14 words)\",\n"
        "  \"clips\": [\n"
        "    \"Clip 1 main commentary (25-32 words explaining the action and why it is crazy)\",\n"
        "    \"Clip 2 main commentary (25-32 words explaining the second clip)\",\n"
        "    \"Clip 3 main commentary (25-32 words explaining the third clip and ending with a loop)\"\n"
        "  ]\n"
        "}"
    )
    data = call_llm_json(prompt)
    if data and isinstance(data.get("clips"), list) and len(data["clips"]) >= 3:
        title = clean_ascii(data.get("title", game_cfg["fallback_script"]["title"]))[:85]
        hook = clean_ascii(data.get("hook", game_cfg["fallback_script"]["hook"]))
        clips = [clean_ascii(c) for c in data["clips"][:3]]
        if len(hook.split()) >= 6 and all(len(c.split()) >= 15 for c in clips):
            return {"title": title, "hook": hook, "clips": clips}
    return game_cfg["fallback_script"]

async def synthesize_voice(text, out_mp3):
    for voice in ["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-BrianNeural"]:
        try:
            comm = edge_tts.Communicate(text, voice, rate="+10%")
            await comm.save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000:
                return
        except Exception:
            pass
    try:
        from gtts import gTTS
        gTTS(text=text, lang="en", tld="com").save(out_mp3)
        if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000:
            return
    except Exception:
        pass
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "170", "-w", "/tmp/fb.wav", text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", "/tmp/fb.wav", out_mp3], check=True)

def fmt_ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def build_karaoke_ass(word_timings, ass_path):
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,DejaVu Sans,78,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,540,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = [f"Dialogue: 0,{fmt_ass_time(st)},{fmt_ass_time(en)},Default,,0,0,0,,{w.replace('{','').replace('}','')}" for st, en, w in word_timings]
    open(ass_path, "w").write(header + "\n".join(events) + "\n")

def build_full_video(batch_idx, game_cfg, script_obj, ig_cookie, x_cookie):
    pool = download_creator_clips(game_cfg, ig_cookie, x_cookie, needed=3)

    # 4 parts: [0] Hook (3-4s) + [1] Main Clip 1 (12-14s) + [2] Main Clip 2 (12-14s) + [3] Main Clip 3 (12-14s) = ~42s total
    narration_parts = [script_obj["hook"]] + script_obj["clips"]
    clip_sources = [pool[0], pool[0], pool[1], pool[2]]

    seg_clips, seg_audios, word_timings = [], [], []
    cursor = 0.0

    for p_idx, (narration, src_vid) in enumerate(zip(narration_parts, clip_sources)):
        mp3_path = f"b{batch_idx}_p{p_idx}.mp3"
        asyncio.run(synthesize_voice(narration, mp3_path))
        seg_dur = get_duration(mp3_path) + 0.25
        seg_audios.append(mp3_path)

        words = narration.split()
        if words:
            step = (seg_dur - 0.15) / len(words)
            for w_i, w in enumerate(words):
                word_timings.append((cursor + (w_i * step), cursor + ((w_i + 1) * step), w))

        src_dur = get_duration(src_vid)
        if p_idx == 0:
            st_sec = 0
        else:
            mid_start = 0 if src_dur <= seg_dur + 2 else max(1, int(src_dur * 0.18))
            max_st = max(mid_start + 1, int(src_dur - seg_dur - 1))
            st_sec = random.randint(mid_start, max_st) if max_st > mid_start else 0

        clip_out = f"b{batch_idx}_v{p_idx}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(st_sec), "-t", f"{seg_dur:.2f}",
            "-i", src_vid,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.10:saturation=1.15",
            "-an", "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", clip_out
        ], check=True)
        seg_clips.append(clip_out)
        cursor += seg_dur

    vid_list = f"b{batch_idx}_vlist.txt"
    aud_list = f"b{batch_idx}_alist.txt"
    open(vid_list, "w").write("\n".join([f"file '{c}'" for c in seg_clips]))
    open(aud_list, "w").write("\n".join([f"file '{a}'" for a in seg_audios]))

    merged_v = f"b{batch_idx}_merged_v.mp4"
    merged_a = f"b{batch_idx}_merged_a.m4a"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", vid_list, "-c", "copy", merged_v], check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", aud_list, "-c:a", "aac", "-b:a", "128k", merged_a], check=True)

    ass_path = f"b{batch_idx}_subs.ass"
    build_karaoke_ass(word_timings, ass_path)

    final_mp4 = f"final_{batch_idx}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", merged_v, "-i", merged_a,
        "-vf", f"ass={ass_path}",
        "-map", "0:v", "-map", "1:a", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "copy", final_mp4
    ], check=True)
    print(f"SUCCESS RENDER: {final_mp4} duration = {cursor:.1f}s (Hook + 3 Full Main Content Clips)")
    return final_mp4

def upload_video(final_mp4, title, description, tags, delay_minutes=0):
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
            "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "20"},
            "status": status_body
        },
        media_body=MediaFileUpload(final_mp4, chunksize=-1, resumable=True)
    )
    resp = req.execute()
    mode = f"SCHEDULED (+{delay_minutes}m)" if delay_minutes > 0 else "LIVE NOW"
    print(f"SUCCESS [{mode}] Video ID: {resp.get('id')}")

if __name__ == "__main__":
    if not os.environ.get("DEEPSEEK_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("Set either DEEPSEEK_API_KEY or GEMINI_API_KEY in GitHub Secrets")
    ig_cookie, x_cookie = setup_cookies()
    algo = analyze_channel_algorithm()
    base_delay = 0 if algo["hours_since_last"] >= 3.0 else int((3.0 - algo["hours_since_last"]) * 60) + 5

    chosen_games = random.sample(GAMES, 2)
    for idx, g_cfg in enumerate(chosen_games, start=1):
        script_obj = generate_full_script(g_cfg)
        final_mp4 = build_full_video(idx, g_cfg, script_obj, ig_cookie, x_cookie)
        full_desc = script_obj["hook"] + " " + " ".join(script_obj["clips"]) + "\n\n#shorts #gaming #" + g_cfg["name"].replace(" ", "").lower()
        delay = base_delay if idx == 1 else base_delay + 12
        upload_video(final_mp4, script_obj["title"], full_desc, g_cfg["tags"], delay_minutes=delay)
