import os, re, json, time, random, asyncio, textwrap, subprocess, urllib.parse, xml.etree.ElementTree as ET, requests, edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai

MALE_US_VOICES = [
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-ChristopherNeural",
    "en-US-GuyNeural"
]

CAPTION_STYLES = [
    "FontName=DejaVu Sans,FontSize=25,Bold=1,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=5",
    "FontName=DejaVu Sans,FontSize=24,Bold=1,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=3,Outline=2,Shadow=0,Alignment=5",
    "FontName=DejaVu Sans,FontSize=25,Bold=1,PrimaryColour=&H0000FF66,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=5",
    "FontName=DejaVu Sans,FontSize=25,Bold=1,PrimaryColour=&H00FFFF00,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=5"
]

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🚀 Make Short Now"}, {"text": "➕ Add Video Link"}],
        [{"text": "🔥 Live Hype"}, {"text": "📊 Cloud Status"}],
        [{"text": "📈 YT Stats"}, {"text": "🗑️ Delete Last"}],
        [{"text": "🎯 Focus: GTA 6"}, {"text": "🎯 Focus: Auto"}],
        [{"text": "❓ Help"}, {"text": "❌ Cancel"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

def deliver_to_telegram(text, video_path=None, ig_caption=""):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not token:
        return
    try:
        if chat_id:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": text, "reply_markup": json.dumps(MAIN_KEYBOARD)}, timeout=15)
            if video_path and os.path.exists(video_path):
                with open(video_path, "rb") as vf:
                    requests.post(f"https://api.telegram.org/bot{token}/sendVideo", data={"chat_id": chat_id, "caption": ig_caption[:1000]}, files={"video": vf}, timeout=60)
        if channel_id and video_path and os.path.exists(video_path):
            with open(video_path, "rb") as vf:
                requests.post(f"https://api.telegram.org/bot{token}/sendVideo", data={"chat_id": channel_id, "caption": ig_caption[:1000]}, files={"video": vf}, timeout=60)
    except Exception as e:
        print("Telegram delivery skip:", e)

def publish_instagram_reel(remote_pcloud_path, ig_caption):
    ig_user = os.environ.get("IG_USER_ID", "").strip()
    ig_token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not ig_user or not ig_token:
        return "Skipped (IG_USER_ID / IG_ACCESS_TOKEN not configured)"
    try:
        public_url = subprocess.check_output(["rclone", "link", remote_pcloud_path]).decode().strip()
        # Convert pCloud share link to direct MP4 stream parameter for Meta Graph API
        if "u.pcloud.link" in public_url and "download=" not in public_url:
            public_url += ("&" if "?" in public_url else "?") + "forcedownload=1"
        c_res = requests.post(
            f"https://graph.facebook.com/v21.0/{ig_user}/media",
            data={"media_type": "REELS", "video_url": public_url, "caption": ig_caption, "share_to_feed": "true", "access_token": ig_token},
            timeout=30
        ).json()
        creation_id = c_res.get("id")
        if not creation_id:
            return f"IG Container error: {c_res}"
        for _ in range(12):
            time.sleep(5)
            st = requests.get(f"https://graph.facebook.com/v21.0/{creation_id}", params={"fields": "status_code", "access_token": ig_token}, timeout=15).json()
            if st.get("status_code") == "FINISHED":
                break
        pub = requests.post(
            f"https://graph.facebook.com/v21.0/{ig_user}/media_publish",
            data={"creation_id": creation_id, "access_token": ig_token},
            timeout=30
        ).json()
        return f"Published Reel ID: {pub.get('id', pub)}"
    except Exception as e:
        return f"IG Reel error: {e}"

def fetch_live_hype_context():
    topics = []
    for q in ["GTA+6", "GTA+5", "Minecraft", "Roblox", "Valorant"]:
        try:
            r = requests.get(f"https://news.google.com/rss/search?q={q}+gaming+when:2d&hl=en-US&gl=US&ceid=US:en", timeout=8)
            root = ET.fromstring(r.text)
            for item in root.findall(".//item")[:2]:
                topics.append(item.find("title").text.split(" - ")[0])
        except Exception:
            pass
    return "; ".join(topics[:6]) if topics else "GTA 6 realistic open world details and viral gaming physics"

def ask_ai_brain(prompt):
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9},
                timeout=20
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print("Groq fallback:", e)

    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key:
        for mid in ["qwen/qwen-2.5-72b-instruct:free", "deepseek/deepseek-chat-v3-0324:free"]:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    json={"model": mid, "messages": [{"role": "user", "content": prompt}]},
                    timeout=25
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print("OpenRouter fallback:", mid, e)

    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gem_key:
        client = genai.Client(api_key=gem_key)
        return client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text
    raise RuntimeError("No AI API key succeeded.")

def stream_unique_action_clips(hist, focus):
    conf = os.environ.get("RCLONE_CONF", "").strip()
    if not conf:
        raise RuntimeError("Missing RCLONE_CONF secret!")
    os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
    open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)

    # Merge both cloud folders into one filename-keyed pool. If the same
    # filename exists in both, keep both source choices but only one pool item.
    pool = {}
    for remote in ("mega", "pcloud"):
        try:
            out = subprocess.check_output(
                ["rclone", "lsjson", f"{remote}:GTA_Clips"],
                stderr=subprocess.DEVNULL
            ).decode()
            for item in json.loads(out):
                name = item.get("Name", "")
                if not item.get("IsDir") and name.lower().endswith((".mp4", ".mkv", ".webm")):
                    pool.setdefault(name, []).append(remote)
        except Exception as exc:
            print(f"Could not list {remote}: {exc}")

    if not pool:
        raise RuntimeError("No videos in mega:GTA_Clips or pcloud:GTA_Clips! Add a video in Telegram first.")

    filenames = list(pool)
    focused = [name for name in filenames if focus != "auto" and focus.lower() in name.lower()]
    gta_files = [name for name in filenames if "gta" in name.lower()]
    fname = random.choice(focused) if focused else (
        random.choice(gta_files) if gta_files and random.random() < 0.75 else random.choice(filenames)
    )
    source_remote = random.choice(pool[fname])
    source_path = f"{source_remote}:GTA_Clips/{fname}"
    local_source = "source_video" + (os.path.splitext(fname)[1] or ".mp4")

    # Download from the cloud that actually contains the selected filename.
    subprocess.run(["rclone", "copyto", source_path, local_source], check=True)
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", local_source
    ]).decode().strip()
    dur = float(probe)
    if dur < 15:
        raise RuntimeError(f"Selected source video is too short ({dur:.1f}s): {fname}")

    max_start = max(0, int(dur - 7.2))
    if max_start < 1:
        raise RuntimeError(f"Source video is too short to make two usable cuts: {fname}")
    mid = max_start // 2
    t1 = t2 = 0
    for _ in range(40):
        t1 = random.randint(0, max(0, mid))
        t2 = random.randint(min(max_start, mid + 1), max_start)
        win_key = f"{fname}:{t1//15}:{t2//15}"
        if win_key not in hist["used_windows"]:
            hist["used_windows"].append(win_key)
            break
    else:
        raise RuntimeError(f"No unused clip windows remain for {fname}; add more source videos.")

    for idx, ts in enumerate((t1, t2)):
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(ts), "-t", "7.2",
            "-i", local_source, "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-an", f"cut_{idx}.mp4"
        ], check=True)

    open("concat.txt", "w").write("file 'cut_0.mp4'\nfile 'cut_1.mp4'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
        "-c", "copy", "raw.mp4"
    ], check=True)
    return fname

def generate_viral_package(fname, hist, focus):
    clean_name = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ")
    hype_now = fetch_live_hype_context()
    angles = [
        "Mythbusting (test a popular rumor or physics rule with a bold question at 0:00)",
        "Physics & Realism Comparison (why older/newer engines humiliate competitors)",
        "Quick Tip & Hidden Trick (secret mechanic or hidden detail 99% of players miss)",
        "Did You Know? Lore & Easter Egg (dark backstory or secret developer detail)",
        "Mini Challenge / Clutch Highlight (high-stakes test or impossible clutch)",
        "Epic Fail / Ragdoll Physics Breakdown (why this engine moment went viral)"
    ]
    recent_avoid = ", ".join(hist["used_topics"][-12:])
    prompt = (
        f"You are a viral Tier-1 US gaming creator for YouTube Shorts & Instagram Reels. Source game file: {clean_name}. Focus mode: {focus}.\n"
        f"Live US Gaming Hype Today: {hype_now}.\n"
        f"Format: {random.choice(angles)}.\n"
        f"Avoid repeating these recent topics: [{recent_avoid}].\n"
        "Target metrics: 75%+ stayed-to-watch ratio and 100%+ loop retention on a 14-second video for a high-RPM US/UK/Canada audience.\n"
        "Output ONLY valid JSON with keys: title, top_hook, script, first_comment, ig_caption, tags\n"
        "- title: curiosity-gap YT title under 70 chars ending with #shorts #gaming\n"
        "- top_hook: 4 to 6 words in ALL CAPS for a persistent top banner at 0:00 posing immediate stakes/curiosity (no emojis)\n"
        "- script: EXACTLY 28 to 34 words total (fits 13.5s brisk voiceover). Start instantly with action (no intro). End mid-thought so the final word loops seamlessly back into the first word!\n"
        "- first_comment: 1 short engaging question to pin in comments to spark debate\n"
        "- ig_caption: punchy US-targeted Instagram Reels caption with CTA (Follow for daily gaming secrets!) + 10 high-reach Tier-1 gaming hashtags\n"
        "- tags: list of 8 high-search US gaming tags without #"
    )
    raw = ask_ai_brain(prompt)
    cleaned = re.sub(r"^```json|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    hist["used_topics"].append(data["top_hook"])
    return (
        data["title"][:85],
        data["top_hook"].replace("'", "").replace('"', ""),
        data["script"],
        data.get("first_comment", "Which game should we test next? 👇"),
        data.get("ig_caption", f"{data['title']} 🔥 Follow for daily gaming secrets! #gaming #gta6 #gta5 #reels #gamer #viral"),
        data.get("tags", ["GTA6", "GTA5", "Shorts", "Gaming"])
    )

async def build_voice_and_captions(script, top_hook):
    chosen_voice = random.choice(MALE_US_VOICES)
    communicate = edge_tts.Communicate(script, chosen_voice, rate="+12%", pitch="-1Hz")
    await communicate.save("voice.mp3")

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", "voice.mp3"
    ]).decode().strip()
    total_dur = float(probe)

    words = script.split()
    chunks = [" ".join(words[i:i+2]).upper() for i in range(0, len(words), 2)]
    step = total_dur / max(1, len(chunks))

    def fmt_ts(sec):
        h, m, s = int(sec // 3600), int((sec % 3600) // 60), int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    srt = [f"{i+1}\n{fmt_ts(i*step)} --> {fmt_ts((i+1)*step)}\n{c}\n" for i, c in enumerate(chunks)]
    open("subs.srt", "w").write("\n".join(srt))
    open("hook.txt", "w").write("\n".join(textwrap.wrap(top_hook.upper(), width=22)))

def render_with_dynamic_fx():
    cap_style = random.choice(CAPTION_STYLES)
    vf = (
        "[0:v]setpts=0.95*PTS,scale=1240:2200:flags=lanczos:force_original_aspect_ratio=increase,"
        "crop=1080:1920:x='(iw-ow)/2+15*sin(t*2)':y='(ih-oh)/2',"
        "unsharp=5:5:0.9:5:5:0.0,eq=contrast=1.10:saturation=1.18,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile=hook.txt:"
        "fontcolor=white:fontsize=46:box=1:boxcolor=black@0.80:boxborderw=18:x=(w-text_w)/2:y=190,"
        f"subtitles=subs.srt:force_style='{cap_style}'[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", "raw.mp4", "-i", "voice.mp3",
        "-f", "lavfi", "-i", "sine=frequency=55:sample_rate=44100",
        "-filter_complex",
        vf + ";[2:a]volume=0.04[bg];[1:a][bg]amix=inputs=2:duration=first[a]",
        "-map", "[v]", "-map", "[a]", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "final.mp4"
    ], check=True)

def publish_everywhere(title, script, first_comment, ig_caption, tags, cfg):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    youtube = build("youtube", "v3", credentials=creds)
    desc = f"{script}\n\nSubscribe for daily gaming myths, physics tests, and hidden secrets!\n\n#shorts #gta6 #gta5 #minecraft #gaming #viral"
    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "20"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        },
        media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    )
    resp = req.execute()
    vid_id = resp.get("id")
    cfg["last_video_id"] = vid_id
    print("SUCCESS! Published Short ID:", vid_id)

    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": vid_id, "topLevelComment": {"snippet": {"textOriginal": first_comment}}}}
        ).execute()
    except Exception as e:
        print("Comment post skip:", e)

    pcloud_target = f"pcloud:Ready_Reels/{vid_id}.mp4"
    subprocess.run(["rclone", "copyto", "final.mp4", pcloud_target], check=False)
    ig_status = publish_instagram_reel(pcloud_target, ig_caption)

    summary = (
        f"✅ Published New Short!\n"
        f"Title: {title}\n"
        f"YouTube: https://youtube.com/shorts/{vid_id}\n"
        f"Instagram Reels: {ig_status}"
    )
    deliver_to_telegram(summary, "final.mp4", ig_caption)

if __name__ == "__main__":
    try:
        hist = json.load(open("history.json")) if os.path.exists("history.json") else {"used_windows": [], "used_topics": []}
        cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": "", "pending_url": ""}
        focus = cfg.get("focus", "auto")
        fname = stream_unique_action_clips(hist, focus)
        title, top_hook, script, first_comment, ig_caption, tags = generate_viral_package(fname, hist, focus)
        asyncio.run(build_voice_and_captions(script, top_hook))
        render_with_dynamic_fx()
        publish_everywhere(title, script, first_comment, ig_caption, tags, cfg)
        json.dump({"used_windows": hist["used_windows"][-400:], "used_topics": hist["used_topics"][-100:]}, open("history.json", "w"), indent=2)
        json.dump(cfg, open("config.json", "w"), indent=2)
    except Exception as e:
        deliver_to_telegram(f"⚠️ Pipeline Alert: {e}")
        raise
