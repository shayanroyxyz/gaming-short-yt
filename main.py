from render_engine import render_full_bleed_short
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

        # Never fabricate generic narration when every provider is unavailable.
        raise RuntimeError("All AI providers failed; refusing to publish a generic fallback script.")

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

import os, re, json, time, random, asyncio, textwrap, subprocess, urllib.parse, xml.etree.ElementTree as ET, requests, edge_tts, hashlib, datetime, base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError, ResumableUploadError
from google.auth.transport.requests import Request
import socket
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
    """Choose one cloud clip, download it locally, and validate it before rendering."""
    conf = os.environ.get("RCLONE_CONF", "").strip()
    if not conf:
        raise RuntimeError("Missing RCLONE_CONF secret.")

    config_dir = os.path.expanduser("~/.config/rclone")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "rclone.conf"), "w", encoding="utf-8") as config_file:
        config_file.write(conf)

    pool, remote_errors = [], []
    for remote in ("mega", "pcloud"):
        try:
            raw = subprocess.check_output(
                ["rclone", "lsjson", f"{remote}:GTA_Clips"],
                stderr=subprocess.PIPE, text=True, timeout=90
            )
            for item in json.loads(raw):
                name = item.get("Name", "")
                if not item.get("IsDir") and name.lower().endswith((".mp4", ".mkv", ".webm")):
                    pool.append((remote, name))
        except Exception as exc:
            remote_errors.append(f"{remote}: {type(exc).__name__}")

    if not pool:
        detail = ", ".join(remote_errors) if remote_errors else "No supported video files found"
        raise RuntimeError(f"No source clips available in MEGA/pCloud GTA_Clips ({detail}).")

    # Never select a source file already confirmed as published. Unlike the
    # rolling recent_sources list, this is a hard duplicate-prevention check.
    published_files = set(hist.get("published_source_files", []))
    eligible_pool = [(r, n) for r, n in pool if n not in published_files]
    if not eligible_pool:
        raise RuntimeError("All available cloud clips are already marked as published; refusing a duplicate upload.")
    recent_sources = set(hist.get("used_sources", [])[-30:])
    fresh_pool = [(r, n) for r, n in eligible_pool if f"{r}:{n}" not in recent_sources]
    candidates = fresh_pool or eligible_pool

    focus_key = str(focus or "auto").lower()
    focused = [(r, n) for r, n in candidates if focus_key != "auto" and focus_key in n.lower()]
    if focused:
        remote, fname = random.choice(focused)
    else:
        gta_files = [(r, n) for r, n in candidates if "gta" in n.lower()]
        remote, fname = random.choice(gta_files) if gta_files and random.random() < 0.75 else random.choice(candidates)

    ext = os.path.splitext(fname)[1].lower()
    if ext not in (".mp4", ".mkv", ".webm"):
        raise RuntimeError(f"Unsupported source extension: {ext or '(none)'}")

    local_clip = os.path.join("/tmp", f"gta_source_clip{ext}")
    if os.path.exists(local_clip):
        os.remove(local_clip)

    source_path = f"{remote}:GTA_Clips/{fname}"
    print(f">> Downloading selected source from {remote}: {fname}")
    subprocess.run(
        [
            "rclone", "copyto", source_path, local_clip,
            "--retries", "3", "--low-level-retries", "5",
            "--timeout", "90s", "--contimeout", "30s"
        ],
        check=True, capture_output=True, text=True, timeout=540
    )

    if not os.path.isfile(local_clip) or os.path.getsize(local_clip) < 100_000:
        raise RuntimeError("Cloud download completed without a valid local video file.")

    duration_text = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", local_clip
        ],
        text=True, stderr=subprocess.PIPE, timeout=60
    ).strip()
    try:
        duration = float(duration_text)
    except (TypeError, ValueError):
        raise RuntimeError(f"ffprobe returned an invalid source duration: {duration_text!r}")
    if not (1.0 < duration < 86400):
        raise RuntimeError(f"Source video duration is invalid: {duration_text!r}")

    start_second = 0.0
    source_hash = source_window_hash(fname, start_second, duration)
    uploaded = {entry.get("hash") for entry in hist.get("uploaded_source_windows", []) if isinstance(entry, dict)}
    if source_hash in uploaded:
        raise RuntimeError(f"Duplicate source window already uploaded; skipping: {fname}")
    used_sources = hist.setdefault("used_sources", [])
    used_sources.append(f"{remote}:{fname}")
    hist["used_sources"] = used_sources[-100:]
    print(f">> Source validated: {duration:.2f}s, {os.path.getsize(local_clip)} bytes")
    return fname, local_clip, source_hash, start_second, duration

def _parse_strict_ai_json(raw):
    cleaned = re.sub(r"^\s*\x60{3}(?:json)?\s*|\s*\x60{3}\s*$", "", str(raw).strip(), flags=re.IGNORECASE)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")
    required = ("hook", "script", "title", "comment")
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in required):
        raise ValueError("AI JSON must contain non-empty hook, script, title, and comment strings")
    words = re.findall(r"\b[\w’'-]+\b", data["script"])
    if not 32 <= len(words) <= 38:
        raise ValueError(f"narration must contain 32–38 words; received {len(words)}")
    if not re.search(r"[.!?][\"')\]]?$", data["script"].strip()):
        raise ValueError("narration must end with a complete sentence")
    return data

def analyze_clip_and_generate_package(fname, local_clip, hist, focus):
    """Use sampled frames from the actual source clip; fail closed if visual analysis is unavailable."""
    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gem_key:
        raise RuntimeError("GEMINI_API_KEY is required for gameplay-aware scripts; refusing filename-only narration.")

    duration_text = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", local_clip],
        text=True, timeout=30
    ).strip()
    duration = max(1.0, float(duration_text))
    frame_paths = []
    for index, fraction in enumerate((0.20, 0.50, 0.80), start=1):
        frame_path = f"/tmp/gameplay_frame_{index}.jpg"
        timestamp = min(max(0.0, duration * fraction), max(0.0, duration - 0.1))
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(timestamp), "-i", local_clip,
             "-frames:v", "1", "-vf", "scale=768:-1", "-q:v", "5", frame_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=45
        )
        if not os.path.isfile(frame_path) or os.path.getsize(frame_path) < 1000:
            raise RuntimeError(f"Could not extract gameplay evidence frame {index}.")
        frame_paths.append(frame_path)

    clean_name = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ")
    recent_scripts = hist.get("recent_scripts", [])
    recent_scripts = [x.get("script", "") if isinstance(x, dict) else str(x) for x in recent_scripts[-20:]]
    recent_avoid = "\n".join(f"- {x}" for x in recent_scripts if x)
    hype_now = fetch_live_hype_context()
    prompt = (
        "Write a truthful gaming Short based ONLY on the attached sampled gameplay frames. "
        "Infer only visible events; never invent actions, outcomes, characters, or mechanics. "
        "If ambiguous, describe only what is certain. "
        f"Filename (weak hint only): {clean_name}. Focus: {focus}. Optional trend context: {hype_now}. "
        f"Do not reuse or closely paraphrase these recent scripts:\n{recent_avoid}\n"
        "Return ONLY valid JSON with keys hook, script, title, comment, ig_caption, tags. "
        "hook: 4-6 uppercase words. script: 32-38 spoken words, natural US English, "
        "describe visible gameplay evidence and payoff, complete final sentence. "
        "Avoid generic filler. title under 70 characters; comment one short question; "
        "ig_caption short; tags array. No markdown fences."
    )
    parts = [{"text": prompt}]
    for path in frame_paths:
        with open(path, "rb") as image_file:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_file.read()).decode("ascii")}})
    errors, data = [], None
    for model in ("gemini-3-flash-preview", "gemini-2.5-flash"):
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gem_key}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json"}},
                timeout=60
            )
            if response.status_code != 200:
                errors.append(f"{model}: HTTP {response.status_code} {response.text[:160]}")
                continue
            raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            candidate = _parse_strict_ai_json(raw)
            from difflib import SequenceMatcher
            normalized = re.sub(r"[^a-z0-9 ]", "", candidate["script"].lower())
            if any(SequenceMatcher(None, normalized, re.sub(r"[^a-z0-9 ]", "", old.lower())).ratio() >= 0.78 for old in recent_scripts if old):
                errors.append(f"{model}: narration too similar to a recent script")
                continue
            data = candidate
            print(f">> Gameplay-aware narration generated by {model}; sampled 3 frames.")
            print(f"[narration] {candidate['script']}")
            break
        except Exception as exc:
            errors.append(f"{model}: {type(exc).__name__}: {exc}")
    if data is None:
        raise RuntimeError("Gameplay-aware script generation failed; refusing to publish. " + " | ".join(errors[-4:]))

    title = data["title"].strip()[:85]
    hook = data["hook"].replace("'", "").replace('"', "").strip()
    script = data["script"].strip()
    comment = data["comment"].strip()
    history = hist.setdefault("recent_scripts", [])
    history.append({"source": fname, "script": script, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    hist["recent_scripts"] = history[-30:]
    hist.setdefault("used_topics", []).append(hook)
    caption = data.get("ig_caption") or f"{title} Follow for daily gaming secrets! #gaming #shorts"
    tags = data.get("tags") or ["Gaming", "Shorts"]
    if not isinstance(tags, list):
        tags = ["Gaming", "Shorts"]
    return title, hook, script, comment, caption, tags

def generate_viral_package(fname, hist, focus, local_clip=None):
    if not local_clip:
        raise RuntimeError("A local gameplay clip is required for visual script analysis.")
    return analyze_clip_and_generate_package(fname, local_clip, hist, focus)

def source_window_hash(source_filename, start_second, duration):
    canonical = f"{source_filename}|{float(start_second):.3f}|{float(duration):.3f}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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

def _youtube_error_details(exc):
    """Return a safe, useful API/network error without exposing credentials."""
    if isinstance(exc, HttpError):
        status = getattr(getattr(exc, "resp", None), "status", "unknown")
        try:
            payload = json.loads(exc.content.decode("utf-8", errors="replace"))
            err = payload.get("error", {})
            message = err.get("message", str(exc))
            reasons = [
                item.get("reason", "")
                for item in err.get("errors", [])
                if isinstance(item, dict) and item.get("reason")
            ]
            reason_text = ", ".join(reasons) if reasons else "no API reason supplied"
            return f"HTTP {status}; reason={reason_text}; message={message}"
        except Exception:
            return f"HTTP {status}; {str(exc)}"
    return f"{type(exc).__name__}: {str(exc)}"


def _is_transient_youtube_upload_error(exc):
    """Retry only temporary server/network failures, never auth or quota errors."""
    if isinstance(exc, HttpError):
        status = getattr(getattr(exc, "resp", None), "status", None)
        return status in (500, 502, 503, 504)
    if isinstance(exc, ResumableUploadError):
        status = getattr(getattr(exc, "resp", None), "status", None)
        return status in (500, 502, 503, 504)
    return isinstance(
        exc,
        (TimeoutError, socket.timeout, ConnectionError,
         requests.exceptions.Timeout, requests.exceptions.ConnectionError)
    )


def publish_everywhere(title, script, first_comment, ig_caption, tags, cfg, hist, source_hash, source_filename, start_second, source_duration):
    # Refresh explicitly before creating the YouTube client. invalid_grant and
    # revoked refresh tokens are surfaced clearly and are never retried as uploads.
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    try:
        creds.refresh(Request())
    except Exception as exc:
        detail = _youtube_error_details(exc)
        raise RuntimeError(f"YouTube OAuth token refresh failed: {detail}") from exc

    youtube = build("youtube", "v3", credentials=creds)
    desc = f"{script}\n\nSubscribe for daily gaming myths, physics tests, and hidden secrets!\n\n#shorts #gta6 #gta5 #minecraft #gaming #viral"
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "20"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }

    resp = None
    for attempt in range(1, 4):
        try:
            # Recreate the resumable request for each attempt.
            upload_request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
            )
            resp = upload_request.execute()
            break
        except Exception as exc:
            detail = _youtube_error_details(exc)
            if attempt < 3 and _is_transient_youtube_upload_error(exc):
                delay = 2 ** (attempt - 1)
                print(f"YouTube upload transient failure on attempt {attempt}/3: {detail}; retrying in {delay}s")
                time.sleep(delay)
                continue
            raise RuntimeError(f"YouTube upload failed on attempt {attempt}/3: {detail}") from exc

    vid_id = (resp or {}).get("id")
    if not vid_id:
        raise RuntimeError(f"YouTube upload response did not contain a video ID: {resp!r}")

    cfg["last_video_id"] = vid_id

    # Verify the actual server-side privacy status. This may require the
    # youtube.readonly OAuth scope; if absent, report that exact API error.
    privacy_status = "UNKNOWN"
    privacy_check_detail = ""
    try:
        status_response = youtube.videos().list(part="status", id=vid_id).execute()
        items = status_response.get("items", [])
        if items:
            privacy_status = items[0].get("status", {}).get("privacyStatus", "UNKNOWN")
        else:
            privacy_check_detail = "videos.list returned no item for the uploaded video ID"
    except Exception as exc:
        privacy_check_detail = _youtube_error_details(exc)
        print(f"YouTube upload succeeded, but privacy verification failed: {privacy_check_detail}")

    hist.setdefault("uploaded_source_windows", []).append({
        "hash": source_hash, "source": source_filename,
        "start_second": float(start_second), "duration": float(source_duration),
        "video_id": vid_id,
        "privacy_status": privacy_status,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    hist["uploaded_source_windows"] = hist["uploaded_source_windows"][-500:]
    published_files = hist.setdefault("published_source_files", [])
    if source_filename not in published_files:
        published_files.append(source_filename)
    hist["published_source_files"] = published_files[-1000:]
    with open("history.json", "w", encoding="utf-8") as history_file:
        json.dump(hist, history_file, indent=2)

    print(f"SUCCESS! Uploaded Short ID: {vid_id}; verified privacyStatus={privacy_status}")
    if privacy_check_detail:
        print("YouTube privacy verification detail:", privacy_check_detail)

    comment_status = "Posted"
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": vid_id, "topLevelComment": {"snippet": {"textOriginal": first_comment}}}}
        ).execute()
    except Exception as e:
        comment_detail = _youtube_error_details(e)
        comment_status = f"Skipped: {comment_detail}"
        print("Comment post skip:", comment_detail)

    pcloud_target = f"pcloud:Ready_Reels/{vid_id}.mp4"
    subprocess.run(["rclone", "copyto", "final.mp4", pcloud_target], check=False)
    ig_status = publish_instagram_reel(pcloud_target, ig_caption)

    privacy_line = f"YouTube privacyStatus: {privacy_status}"
    if privacy_check_detail:
        privacy_line += f"\nPrivacy verification error: {privacy_check_detail}"
    summary = (
        f"✅ YouTube upload succeeded!\n"
        f"Title: {title}\n"
        f"YouTube: https://youtube.com/shorts/{vid_id}\n"
        f"{privacy_line}\n"
        f"YouTube pinned comment: {comment_status}\n"
        f"Instagram Reels: {ig_status}"
    )
    deliver_to_telegram(summary, "final.mp4", ig_caption)

if __name__ == "__main__":
    try:
        hist = json.load(open("history.json")) if os.path.exists("history.json") else {"used_windows": [], "used_topics": []}
        cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": "", "pending_url": ""}
        focus = cfg.get("focus", "auto")
        fname, local_clip, source_hash, start_second, source_duration = stream_unique_action_clips(hist, focus)
        title, top_hook, script, first_comment, ig_caption, tags = generate_viral_package(fname, hist, focus, local_clip)
        rendered_path = render_full_bleed_short(local_clip, script, "final.mp4", top_hook=top_hook)
        if not os.path.isfile(rendered_path) or os.path.getsize(rendered_path) < 100_000:
            raise RuntimeError("Render step returned without a valid final video.")
        final_duration = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", rendered_path],
            text=True, timeout=60
        ).strip())
        if not (1.0 < final_duration < 180.0):
            raise RuntimeError(f"Rendered Short duration is outside the expected range: {final_duration:.2f}s")
        publish_everywhere(title, script, first_comment, ig_caption, tags, cfg, hist, source_hash, fname, start_second, source_duration)
        with open("history.json", "w", encoding="utf-8") as history_file:
            json.dump({"used_windows": hist.get("used_windows", [])[-400:],
                       "used_topics": hist.get("used_topics", [])[-100:],
                       "recent_scripts": hist.get("recent_scripts", [])[-30:],
                       "used_sources": hist.get("used_sources", [])[-100:],
                       "uploaded_source_windows": hist.get("uploaded_source_windows", [])[-500:],
                       "published_source_files": hist.get("published_source_files", [])[-1000:]},
                      history_file, indent=2)
        with open("config.json", "w", encoding="utf-8") as config_file:
            json.dump(cfg, config_file, indent=2)
    except Exception as e:
        deliver_to_telegram(f"⚠️ Pipeline Alert: {e}")
        raise
