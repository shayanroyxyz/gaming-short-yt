import os, re, json, time, random, asyncio, subprocess, datetime, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
from analyzer import analyze_channel_algorithm

GAMES = [
    {
        "name": "GTA 5",
        "search": "GTA 5 gameplay myths mods",
        "subs": ["GTAV", "gtaonline"],
        "tags": ["GTA5", "GTAMyths", "GTA5Gameplay", "RockstarGames", "Shorts"],
        "fallback_myths": [
            {"search_kw": "GTA 5 vending machine gameplay", "narration": "GTA 5 myth number one. A vending machine runs out of stock after ten sodas. Let us test it right now... myth confirmed."},
            {"search_kw": "GTA 5 character switch gameplay", "narration": "Myth number two. Punching a locked door and switching characters teleports you inside. Watch closely... myth confirmed."},
            {"search_kw": "GTA 5 swimming pool RPG gameplay", "narration": "Myth number three. Firing a rocket straight into a pool makes it bounce in the air. Here goes... myth confirmed."}
        ]
    },
    {
        "name": "Minecraft",
        "search": "Minecraft gameplay facts myths",
        "subs": ["Minecraft", "MinecraftMemes"],
        "tags": ["Minecraft", "MinecraftFacts", "MinecraftMyths", "Gaming", "Shorts"],
        "fallback_myths": [
            {"search_kw": "Minecraft bedrock creeper gameplay", "narration": "Minecraft fact number one. Creepers are actually afraid of ocelots and cats and will sprint away on sight... fact confirmed."},
            {"search_kw": "Minecraft enderman water gameplay", "narration": "Fact number two. Endermen take damage from rain and water but never drown in lava... fact confirmed."},
            {"search_kw": "Minecraft nether bed explosion gameplay", "narration": "Fact number three. Sleeping in the Nether creates an explosion bigger than TNT. Watch this... fact confirmed."}
        ]
    },
    {
        "name": "Roblox",
        "search": "Roblox gameplay secrets facts",
        "subs": ["roblox", "RobloxMemes"],
        "tags": ["Roblox", "RobloxFacts", "RobloxSecrets", "Gaming", "Shorts"],
        "fallback_myths": [
            {"search_kw": "Roblox Brookhaven secret gameplay", "narration": "Roblox secret number one. Hidden underneath the Brookhaven hospital is an abandoned agency room nobody finds... secret confirmed."},
            {"search_kw": "Roblox Blox Fruits gameplay", "narration": "Secret number two. Certain Roblox games hide secret developer badges behind invisible walls. Look right here... secret confirmed."},
            {"search_kw": "Roblox obby physics gameplay", "narration": "Secret number three. Tilting your camera sideways lets you clip through thin corners in classic obbies... secret confirmed."}
        ]
    }
]

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
        return min(w, h) >= 360 and get_duration(path) >= 12.0
    except Exception:
        return False

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
            except Exception as e:
                print(f"{m_name} retry: {e}")
                time.sleep(2)
    return None

def generate_storyboard(game_cfg):
    prompt = (
        f"Create a fast-paced 35-to-45 second YouTube Short testing 3 viral myths or hidden facts in {game_cfg['name']} (like classic myth-busting gameplay Shorts).\n"
        "Return ONLY valid JSON with this exact schema:\n"
        "{\n"
        f"  \"title\": \"Catchy YouTube Short title under 70 chars about {game_cfg['name']} myths ending with #shorts\","
        "  \"segments\": [\n"
        f"    {{\"search_kw\": \"{game_cfg['name']} gameplay keyword\", \"narration\": \"Myth number one... (25-32 words testing a specific in-game mechanic and saying myth confirmed or busted)\"}},\n"
        f"    {{\"search_kw\": \"{game_cfg['name']} gameplay keyword\", \"narration\": \"Myth number two... (25-32 words testing a second mechanic and saying myth confirmed or busted)\"}},\n"
        f"    {{\"search_kw\": \"{game_cfg['name']} gameplay keyword\", \"narration\": \"Myth number three... (25-32 words testing a third mechanic and saying myth confirmed or busted)\"}}\n"
        "  ]\n"
        "}"
    )
    data = call_llm_json(prompt)
    if data and isinstance(data.get("segments"), list) and len(data["segments"]) >= 3:
        title = clean_ascii(data.get("title", f"Testing 3 Viral {game_cfg['name']} Myths! #shorts"))[:85]
        segs = []
        for s in data["segments"][:3]:
            segs.append({
                "search_kw": clean_ascii(s.get("search_kw", game_cfg["search"])),
                "narration": clean_ascii(s.get("narration", ""))
            })
        if all(len(s["narration"].split()) >= 10 for s in segs):
            return title, segs

    return f"Busting 3 Viral {game_cfg['name']} Myths! #shorts", game_cfg["fallback_myths"]

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

def download_gameplay_pool(game_cfg, needed=3):
    pool = []
    # 1. Dailymotion strict gameplay search (unblocked on GitHub Actions, >=360p, rejects real-life/unboxings)
    q = requests.utils.quote(game_cfg["search"])
    dm_url = f"https://www.dailymotion.com/search/{q}/videos"
    for idx in range(1, 8):
        if len(pool) >= needed:
            break
        out_f = f"pool_{game_cfg['name'].replace(' ','_')}_{idx}.mp4"
        if os.path.exists(out_f):
            os.remove(out_f)
        try:
            subprocess.run([
                "yt-dlp", "--no-warnings", "--socket-timeout", "15",
                "--playlist-items", str(idx),
                "--match-title", f"(?i)({game_cfg['name'].split()[0]}|gameplay|myths|mod)",
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

    # 2. Reddit gaming subreddit fallback (>=360p gameplay videos)
    if len(pool) < needed:
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36"}
        for sub in game_cfg["subs"]:
            try:
                r = requests.get(f"https://www.reddit.com/r/{sub}/top.json?t=month&limit=40", headers=headers, timeout=12)
                if r.status_code != 200:
                    continue
                posts = r.json().get("data", {}).get("children", [])
                random.shuffle(posts)
                for p in posts:
                    if len(pool) >= needed:
                        break
                    d = p.get("data", {})
                    rv = (d.get("media") or {}).get("reddit_video") or {}
                    fb = rv.get("fallback_url")
                    if d.get("is_video") and fb and int(rv.get("height") or 0) >= 360 and float(rv.get("duration") or 0) >= 12:
                        out_f = f"pool_rd_{len(pool)}_{random.randint(100,999)}.mp4"
                        subprocess.run(["curl", "-m", "25", "-L", "-f", "-s", "-A", headers["User-Agent"], fb, "-o", out_f])
                        if valid_gameplay_video(out_f):
                            pool.append(out_f)
            except Exception:
                pass

    if not pool:
        raise RuntimeError(f"No >=360p gameplay found for {game_cfg['name']}")
    while len(pool) < needed:
        pool.append(random.choice(pool))
    return pool

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
    events = []
    for start_t, end_t, word in word_timings:
        clean_w = word.replace("{", "").replace("}", "")
        events.append(f"Dialogue: 0,{fmt_ass_time(start_t)},{fmt_ass_time(end_t)},Default,,0,0,0,,{clean_w}")
    open(ass_path, "w").write(header + "\n".join(events) + "\n")

def build_full_video(batch_idx, game_cfg, segments):
    pool = download_gameplay_pool(game_cfg, needed=3)
    seg_clips = []
    seg_audios = []
    word_timings = []
    cursor = 0.0

    for s_idx, seg in enumerate(segments):
        mp3_path = f"b{batch_idx}_s{s_idx}.mp3"
        asyncio.run(synthesize_voice(seg["narration"], mp3_path))
        seg_dur = get_duration(mp3_path) + 0.25
        seg_audios.append(mp3_path)

        # Map each word to exact timestamp so captions pop in center screen just like reference video
        words = seg["narration"].split()
        if words:
            step = (seg_dur - 0.15) / len(words)
            for w_i, w in enumerate(words):
                st = cursor + (w_i * step)
                en = cursor + ((w_i + 1) * step)
                word_timings.append((st, en, w))

        # Slice gameplay clip matching exact segment duration (12-16s per myth = ~40-46s full video)
        src_vid = pool[s_idx % len(pool)]
        src_dur = get_duration(src_vid)
        mid_start = max(2, int(src_dur * 0.20))
        max_st = max(mid_start + 1, int(src_dur - seg_dur - 2))
        st_sec = random.randint(mid_start, max_st) if max_st > mid_start else 0

        clip_out = f"b{batch_idx}_c{s_idx}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(st_sec), "-t", f"{seg_dur:.2f}",
            "-i", src_vid,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.10:saturation=1.15",
            "-an", "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", clip_out
        ], check=True)
        seg_clips.append(clip_out)
        cursor += seg_dur

    # Concatenate all 3 gameplay clips and all 3 voiceover segments
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
    print(f"Rendered full {cursor:.1f}s multi-myth Short: {final_mp4}")
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
    algo = analyze_channel_algorithm()
    base_delay = 0 if algo["hours_since_last"] >= 3.0 else int((3.0 - algo["hours_since_last"]) * 60) + 5

    chosen_games = random.sample(GAMES, 2)
    for idx, g_cfg in enumerate(chosen_games, start=1):
        title, segments = generate_storyboard(g_cfg)
        final_mp4 = build_full_video(idx, g_cfg, segments)
        full_desc = " ".join(s["narration"] for s in segments) + "\n\n#shorts #gaming #" + g_cfg["name"].replace(" ", "").lower()
        delay = base_delay if idx == 1 else base_delay + 12
        upload_video(final_mp4, title, full_desc, g_cfg["tags"], delay_minutes=delay)
