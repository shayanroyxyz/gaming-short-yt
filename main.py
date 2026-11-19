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

def send_telegram_with_buttons(text, video_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    kb = json.dumps({
        "inline_keyboard": [
            [{"text": "🚀 Make Another Now", "callback_data": "MAKE_NOW"}, {"text": "📈 Channel Stats", "callback_data": "STATS"}],
            [{"text": "🗑️ Delete Last Short", "callback_data": "DELETE_LAST"}]
        ]
    })
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": text, "reply_markup": kb}, timeout=15)
        if video_path and os.path.exists(video_path):
            with open(video_path, "rb") as vf:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat_id, "caption": "Tap Share -> Instagram Reels to cross-post!"},
                    files={"video": vf},
                    timeout=60
                )
    except Exception as e:
        print("Telegram notify skip:", e)

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
    os.makedirs(os.path.expanduser("~/.config/rclone"), exist_ok=True)
    open(os.path.expanduser("~/.config/rclone/rclone.conf"), "w").write(conf)

    pool = []
    for remote in ["mega", "pcloud"]:
        try:
            out = subprocess.check_output(["rclone", "lsjson", f"{remote}:GTA_Clips"], stderr=subprocess.DEVNULL).decode()
            for f in json.loads(out):
                if not f.get("IsDir") and f["Name"].lower().endswith((".mp4", ".mkv", ".webm")):
                    pool.append((remote, f["Name"]))
        except Exception:
            pass

    if not pool:
        raise RuntimeError("No videos found in mega:GTA_Clips or pcloud:GTA_Clips! Send a YouTube link to your Telegram bot first.")

    focused = [x for x in pool if focus != "auto" and focus in x[1].lower()]
    if focused:
        remote, fname = random.choice(focused)
    else:
        gta_files = [x for x in pool if "gta" in x[1].lower()]
        remote, fname = random.choice(gta_files) if (gta_files and random.random() < 0.75) else random.choice(pool)

    srv = subprocess.Popen(["rclone", "serve", "http", f"{remote}:GTA_Clips", "--addr", "127.0.0.1:8080"])
    try:
        time.sleep(3)
        url = f"http://127.0.0.1:8080/{urllib.parse.quote(fname)}"
        probe = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", url
        ]).decode().strip()
        dur = float(probe)

        safe_start = int(dur * 0.06)
        safe_end = max(safe_start + 25, int(dur * 0.92))
        mid = (safe_start + safe_end) // 2

        for _ in range(20):
            t1 = random.randint(safe_start, max(safe_start, mid - 10))
            t2 = random.randint(mid, max(mid, safe_end - 10))
            win_key = f"{fname}:{t1//15}:{t2//15}"
            if win_key not in hist["used_windows"]:
                hist["used_windows"].append(win_key)
                break

        for idx, ts in enumerate([t1, t2]):
            subprocess.run([
                "ffmpeg", "-y", "-ss", str(ts), "-t", "7.2",
                "-i", url, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", f"cut_{idx}.mp4"
            ], check=True)

        open("concat.txt", "w").write("file 'cut_0.mp4'\nfile 'cut_1.mp4'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "raw.mp4"], check=True)
    finally:
        srv.terminate()
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
        f"You are a viral US gaming YouTube Shorts strategist. Source game file: {clean_name}. Focus mode: {focus}.\n"
        f"Live US Gaming Hype Today: {hype_now}.\n"
        f"Format: {random.choice(angles)}.\n"
        f"Avoid repeating these recent topics: [{recent_avoid}].\n"
        "Target metrics: 75%+ stayed-to-watch ratio and 100%+ loop retention on a 14-second Short for a high-RPM US audience.\n"
        "Output ONLY valid JSON with keys: title, top_hook, script, first_comment, tags\n"
        "- title: curiosity-gap title under 70 chars ending with #shorts #gaming\n"
        "- top_hook: 4 to 6 words in ALL CAPS for a persistent top banner at 0:00 posing immediate stakes/curiosity (no emojis)\n"
        "- script: EXACTLY 28 to 34 words total (fits 13.5s brisk voiceover). Start instantly with action (no intro). End mid-thought so the final word loops seamlessly back into the first word!\n"
        "- first_comment: 1 short engaging question to pin in comments to spark debate\n"
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

def publish_everywhere(title, script, first_comment, tags, cfg):
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

    # Auto-post engagement comment in first 60s
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": vid_id, "topLevelComment": {"snippet": {"textOriginal": first_comment}}}}
        ).execute()
    except Exception as e:
        print("Comment post skip (needs youtube.force-ssl scope):", e)

    subprocess.run(["rclone", "copyto", "final.mp4", f"pcloud:Ready_Reels/{vid_id}.mp4"], check=False)
    send_telegram_with_buttons(f"✅ Published New Short!\nTitle: {title}\nURL: https://youtube.com/shorts/{vid_id}", "final.mp4")

if __name__ == "__main__":
    try:
        hist = load_history() if os.path.exists("history.json") else {"used_windows": [], "used_topics": []}
        cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": ""}
        focus = cfg.get("focus", "auto")
        fname = stream_unique_action_clips(hist, focus)
        title, top_hook, script, first_comment, tags = generate_viral_package(fname, hist, focus)
        asyncio.run(build_voice_and_captions(script, top_hook))
        render_with_dynamic_fx()
        publish_everywhere(title, script, first_comment, tags, cfg)
        json.dump({"used_windows": hist["used_windows"][-400:], "used_topics": hist["used_topics"][-100:]}, open("history.json", "w"), indent=2)
        json.dump(cfg, open("config.json", "w"), indent=2)
    except Exception as e:
        send_telegram_with_buttons(f"⚠️ Pipeline Alert: {e}")
        raise
