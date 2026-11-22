from render_engine import render_blur_landscape_short
# === BULLETPROOF 3-AI WATERFALL MONKEYPATCH ===
import os as _os, requests as _req
try:
    from google.genai import models as _gmodels
    _orig_gen = _gmodels.Models.generate_content

    def _waterfall_generate(self, *args, **kwargs):
        contents = kwargs.get("contents") if "contents" in kwargs else (args[1] if len(args) > 1 else "")
        prompt_str = contents if isinstance(contents, str) else str(contents)

        # 1. Try Groq first (fastest, free)
        gk = _os.environ.get("GROQ_API_KEY", "").strip()
        if gk:
            try:
                r = _req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {gk}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt_str}], "temperature": 0.85},
                    timeout=25
                )
                if r.status_code == 200:
                    t = r.json()["choices"][0]["message"]["content"].strip()
                    if t:
                        print(">> AI Brain Used: GROQ (llama-3.3-70b-versatile)")
                        return type("Resp", (), {"text": t})()
                else:
                    print(f">> Groq status {r.status_code}: {r.text[:120]}")
            except Exception as e:
                print(f">> Groq error: {e}")

        # 2. Try OpenRouter free models
        ok = _os.environ.get("OPENROUTER_API_KEY", "").strip()
        if ok:
            for m in ["qwen/qwen-2.5-72b-instruct:free", "deepseek/deepseek-chat:free", "meta-llama/llama-3.3-70b-instruct:free"]:
                try:
                    r = _req.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {ok}", "Content-Type": "application/json"},
                        json={"model": m, "messages": [{"role": "user", "content": prompt_str}]},
                        timeout=30
                    )
                    if r.status_code == 200:
                        t = r.json()["choices"][0]["message"]["content"].strip()
                        if t:
                            print(f">> AI Brain Used: OPENROUTER ({m})")
                            return type("Resp", (), {"text": t})()
                except Exception as e:
                    print(f">> OpenRouter {m} error: {e}")

        # 3. Try Gemini REST across all active models
        gemk = _os.environ.get("GEMINI_API_KEY", "").strip()
        if gemk:
            for gm in ["gemini-3.8-flash", "gemini-3-flash-preview", "gemini-2.5-flash-lite", "gemini-2.0-flash"]:
                try:
                    r = _req.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{gm}:generateContent?key={gemk}",
                        headers={"Content-Type": "application/json"},
                        json={"contents": [{"parts": [{"text": prompt_str}]}]},
                        timeout=25
                    )
                    if r.status_code == 200:
                        t = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if t:
                            print(f">> AI Brain Used: GEMINI ({gm})")
                            return type("Resp", (), {"text": t})()
                    else:
                        print(f">> Gemini {gm} status {r.status_code}: {r.text[:100]}")
                except Exception as e:
                    print(f">> Gemini {gm} error: {e}")

        # 4. Offline emergency script fallback so pipeline NEVER crashes
        print(">> AI Brain Used: OFFLINE FALLBACK")
        fallback_json = '{"hook": "NOBODY SURVIVES THIS TEST", "script": "Ninety-nine percent of players think they know how this game works until you push the physics engine to its absolute limit and watch what happens next when", "title": "Insane Gaming Physics Myth Tested! #shorts #gaming", "comment": "Did you expect that ending? Comment below!"}'
        return type("Resp", (), {"text": fallback_json})()

    _gmodels.Models.generate_content = _waterfall_generate
except Exception as _patch_err:
    print("Monkeypatch warning:", _patch_err)
# === END MONKEYPATCH ===


def generate_viral_script_waterfall(prompt_text):
    import os, requests
    # Tier 1: Groq (Fastest, 1000/day free)
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt_text}], "temperature": 0.85},
                timeout=25
            )
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"].strip()
                if txt:
                    print("AI Brain Active: Groq llama-3.3-70b")
                    return txt
        except Exception as e:
            print(f"Groq fallback: {e}")

    # Tier 2: OpenRouter (Free models)
    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key:
        for or_model in ["qwen/qwen-2.5-72b-instruct:free", "deepseek/deepseek-chat:free", "meta-llama/llama-3.3-70b-instruct:free"]:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    json={"model": or_model, "messages": [{"role": "user", "content": prompt_text}]},
                    timeout=30
                )
                if r.status_code == 200:
                    txt = r.json()["choices"][0]["message"]["content"].strip()
                    if txt:
                        print(f"AI Brain Active: OpenRouter {or_model}")
                        return txt
            except Exception as e:
                print(f"OpenRouter {or_model} fallback: {e}")

    # Tier 3: Gemini (Multi-model auto-fallback)
    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gem_key:
        for g_model in ["gemini-3.8-flash", "gemini-3-flash-preview", "gemini-3.8-flash-lite", "gemini-2.0-flash"]:
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={gem_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt_text}]}]},
                    timeout=25
                )
                if r.status_code == 200:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if txt:
                        print(f"AI Brain Active: Gemini {g_model}")
                        return txt
            except Exception as e:
                print(f"Gemini {g_model} fallback: {e}")
    return None

class _SafeModelsProxy:
    def __init__(self, real_models):
        self._real = real_models
    def generate_content(self, *args, **kwargs):
        prompt_text = kwargs.get("contents") or (args[1] if len(args) > 1 else "")
        if isinstance(prompt_text, str) and prompt_text.strip():
            out = generate_viral_script_waterfall(prompt_text)
            if out:
                return type("Resp", (), {"text": out})()
        return self._real.generate_content(*args, **kwargs)

class _SafeClientProxy:
    def __init__(self, real_client):
        self.models = _SafeModelsProxy(real_client.models)

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
        client = _SafeClientProxy(genai.Client(api_key=gem_key))
        return client.models.generate_content(model="gemini-3.8-flash", contents=prompt).text
    raise RuntimeError("No AI API key succeeded.")

def stream_unique_action_clips(hist, focus):
    conf = os.environ.get("RCLONE_CONF", "").strip()
    if not conf:
        raise RuntimeError("Missing RCLONE_CONF secret!")
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
        raise RuntimeError("No videos in mega:GTA_Clips or pcloud:GTA_Clips! Paste a YouTube link in Telegram first.")

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
            render_blur_landscape_short(local_clip, script_text, output_path)

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
