import render_engine as _render_engine
from render_engine import render_full_bleed_short
# Keep SDK text calls on the same discovered-model fallback path.
import os as _os
try:
    from google.genai import models as _gmodels
    def _waterfall_generate(self, *args, **kwargs):
        prompt = kwargs.get("contents") if "contents" in kwargs else (args[1] if len(args) > 1 else "")
        prompt_text = prompt if isinstance(prompt, str) else str(prompt)
        result = generate_viral_script_waterfall(prompt_text)
        if result:
            return type("Resp", (), {"text": result})()
        raise RuntimeError("All configured AI providers failed.")
    _gmodels.Models.generate_content = _waterfall_generate
except Exception as _patch_err:
    print("AI fallback wrapper warning:", _patch_err)



def generate_viral_script_waterfall(prompt_text):
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        for model in _discover_groq_models(groq_key):
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt_text}], "temperature": 0.8},
                    timeout=35
                )
                if response.status_code == 200:
                    text_out = response.json()["choices"][0]["message"]["content"].strip()
                    if text_out:
                        print(f"[AI] Groq model selected: {model}")
                        return text_out
                else:
                    print(f"[AI] Groq {model} HTTP {response.status_code}: {response.text[:120]}")
            except Exception as exc:
                print(f"[AI] Groq {model}: {type(exc).__name__}: {exc}")

    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key:
        for model in ("qwen/qwen-2.5-72b-instruct:free", "deepseek/deepseek-chat:free",
                      "meta-llama/llama-3.3-70b-instruct:free"):
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt_text}], "temperature": 0.8},
                    timeout=35
                )
                if response.status_code == 200:
                    text_out = response.json()["choices"][0]["message"]["content"].strip()
                    if text_out:
                        return text_out
            except Exception as exc:
                print(f"[AI] OpenRouter {model}: {type(exc).__name__}: {exc}")

    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gem_key:
        _, generated = _gemini_generate(gem_key, [{"text": prompt_text}])
        if generated:
            return generated
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

def _discover_gemini_models(api_key):
    """Return available generateContent Flash/Pro models, discovered from this key."""
    try:
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 1000}, timeout=20
        )
        if response.status_code in (401, 403):
            print(f"[AI] Gemini model discovery unauthorized (HTTP {response.status_code}); handing off to Groq/OpenRouter.", flush=True)
            return []
        response.raise_for_status()
        models = response.json().get("models", [])
        eligible = []
        for item in models:
            name = str(item.get("name", "")).replace("models/", "")
            methods = item.get("supportedGenerationMethods", [])
            low = name.lower()
            if "generateContent" not in methods or not ("flash" in low or "pro" in low):
                continue
            if "embedding" in low or "tts" in low or "image" in low:
                continue
            eligible.append(name)
        eligible.sort(key=lambda n: (
            0 if "flash" in n.lower() and "preview" not in n.lower() else
            1 if "flash" in n.lower() else 2 if "pro" in n.lower() else 3, n
        ))
        return eligible
    except Exception as exc:
        print(f"[AI] Gemini model discovery failed: {type(exc).__name__}: {exc}")
        return []


def _discover_groq_models(api_key):
    """Discover active Groq chat models instead of relying on retired model IDs."""
    try:
        response = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=20
        )
        response.raise_for_status()
        rows = response.json().get("data", [])
        preferred = []
        for item in rows:
            model_id = str(item.get("id", "")).strip()
            if not model_id:
                continue
            if item.get("active") is False:
                continue
            low = model_id.lower()
            # Groq's model catalog also contains Llama Prompt Guard models.
            # They are classifiers, not chat-generation models, and return
            # HTTP 400 when used with chat/completions.
            if any(term in low for term in ("prompt-guard", "llama-guard", "safeguard", "guardrail", "moderation")):
                continue
            if any(term in low for term in ("llama", "qwen", "mixtral", "gemma")):
                preferred.append(model_id)
        preferred.sort(key=lambda n: (
            0 if "llama" in n.lower() else 1 if "qwen" in n.lower() else
            2 if "mixtral" in n.lower() else 3, n
        ))
        return preferred[:8]
    except Exception as exc:
        print(f"[AI] Groq model discovery failed: {type(exc).__name__}: {exc}")
        return []


def _gemini_generate(api_key, parts, generation_config=None):
    """Try discovered Gemini models with short exponential backoff on overload."""
    models = _discover_gemini_models(api_key)
    if not models:
        print("[AI] No Gemini Flash/Pro generateContent models are available for this API key.")
        return None, None
    for model in models:
        for attempt in range(3):
            try:
                payload = {"contents": [{"parts": parts}]}
                if generation_config:
                    payload["generationConfig"] = generation_config
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": api_key},
                    headers={"Content-Type": "application/json"},
                    json=payload, timeout=60
                )
                if response.status_code in (401, 403):
                    print(f"[AI] Gemini {model} unauthorized (HTTP {response.status_code}); handing off to Groq/OpenRouter.", flush=True)
                    return None, None
                if response.status_code == 503 or response.status_code == 429:
                    if attempt < 2:
                        delay = 2 ** attempt
                        print(f"[AI] Gemini {model} overloaded ({response.status_code}); retrying in {delay}s")
                        time.sleep(delay)
                        continue
                if response.status_code != 200:
                    print(f"[AI] Gemini {model} HTTP {response.status_code}: {response.text[:140]}")
                    break
                candidates = response.json().get("candidates", [])
                if candidates:
                    text_parts = candidates[0].get("content", {}).get("parts", [])
                    generated = "\n".join(p.get("text", "") for p in text_parts if p.get("text"))
                    if generated.strip():
                        return model, generated.strip()
                break
            except Exception as exc:
                print(f"[AI] Gemini {model} attempt {attempt + 1}: {type(exc).__name__}: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
    return None, None


def _repair_title(title, game_label="GTA"):
    """Sanitize title text and guarantee a concise curiosity trigger."""
    value = re.sub(r"\s+", " ", str(title or "")).strip(" \t\r\n-—:|")
    value = re.sub(r"[<>\[\]{}]", "", value)
    banned = re.compile(
        r"\b(?:tracking leads through the city|from the beach|pushing physics|"
        r"gaming moments|epic gameplay|crazy gameplay|a day in|exploring the city)\b",
        re.IGNORECASE
    )
    if banned.search(value):
        value = ""
    if not value:
        value = f"{game_label}: What Happens Next?"
    trigger = re.compile(
        r"\b(?:\d+|secret|hidden|rarest|easter egg|why|how|never|actually|"
        r"still|vs\.?|beat|forgotten|only|impossible|mystery|truth|most|next)\b",
        re.IGNORECASE
    )
    if not trigger.search(value):
        suffix = " — What Happens Next?"
        value = value[:max(1, 70 - len(suffix))].rstrip(" -—:") + suffix
    return value[:70].rstrip(" -—:?!") + ("?" if not value.endswith(("?", "!")) else "")


def _offline_package(fname, focus):
    """Conservative last-resort narration; makes no claims about unseen gameplay details."""
    stem = os.path.splitext(os.path.basename(fname))[0]
    match = re.search(r"\[(.*?)\]", stem)
    game = (match.group(1).replace("6", " 6").strip() if match else "Gaming")
    game = re.sub(r"[^A-Za-z0-9 ]", " ", game).strip() or "Gaming"
    script = (
        f"This moment shows why {game} keeps players coming back. "
        "The world gives every small decision room to become something unexpected. "
        "There is no need for a scripted cutscene when the game systems create their own stories. "
        "Watch the details, notice how the moment unfolds, and decide what stands out most. "
        "That unpredictability is the reason these games are still worth revisiting."
    )
    words = re.findall(r"\b[\w’'-]+\b", script)
    if len(words) < 55:
        script += " Every playthrough can feel a little different."
    return {
        "creative_angle": "story_fact",
        "hook": f"{game} Moment",
        "script": script,
        "title": _repair_title(f"{game}: What Happens Next?", game),
        "comment": "Which detail stood out to you?",
        "ig_caption": f"{game} gameplay moment. #gaming #shorts",
        "tags": ["Gaming", "Shorts", game]
    }


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
    """Use dynamically discovered free providers; return None if all are unavailable."""
    return generate_viral_script_waterfall(prompt)

def stream_unique_action_clips(hist, focus):
    """Download a cloud source and extract a fresh, non-overlapping window up to 65 seconds."""
    max_window_seconds = 65.0
    min_window_seconds = 58.5
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

    # Probe each cloud source's duration before selecting it. Use a 65s window
    # when available (at least 58.5s is required for the longest supported Short).
    random.shuffle(pool)
    focus_key = str(focus or "auto").lower()
    focused_pool = [(r, n) for r, n in pool if focus_key != "auto" and focus_key in n.lower()]
    if focused_pool:
        pool = focused_pool + [item for item in pool if item not in focused_pool]

    uploaded_entries = [
        entry for entry in (hist.get("uploaded_source_windows", []) + hist.get("used_source_windows", []))
        if isinstance(entry, dict)
    ]
    used_sources = hist.setdefault("used_sources", [])

    chosen = None
    exhausted_files = []
    for remote, fname in pool:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".mp4", ".mkv", ".webm"):
            continue
        source_key = f"{remote}:{fname}"
        local_full = os.path.join("/tmp", f"gta_source_{remote}_{hashlib.sha1(fname.encode('utf-8')).hexdigest()[:10]}{ext}")
        try:
            if os.path.exists(local_full):
                os.remove(local_full)
            print(f">> Downloading selected source from {remote}: {fname}")
            subprocess.run(
                ["rclone", "copyto", f"{remote}:GTA_Clips/{fname}", local_full,
                 "--retries", "3", "--low-level-retries", "5",
                 "--timeout", "90s", "--contimeout", "30s"],
                check=True, capture_output=True, text=True, timeout=540
            )
            if not os.path.isfile(local_full) or os.path.getsize(local_full) < 100_000:
                raise RuntimeError("download did not produce a valid local video file")
            duration_text = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", local_full],
                text=True, stderr=subprocess.PIPE, timeout=60
            ).strip()
            duration = float(duration_text)
            if not (min_window_seconds <= duration < 86400):
                print(f">> Skipping {source_key}: source is shorter than {min_window_seconds:.0f}s ({duration:.2f}s).")
                continue
            window_seconds = min(max_window_seconds, duration)
            starts_used = []
            for entry in uploaded_entries:
                entry_source = str(entry.get("source", ""))
                if entry_source == source_key:
                    try:
                        starts_used.append(float(entry.get("start_second", 0.0)))
                    except (TypeError, ValueError):
                        continue
            window_count = int((duration - window_seconds) // max_window_seconds) + 1
            candidate_starts = [float(i * max_window_seconds) for i in range(window_count)]
            available_starts = [
                start for start in candidate_starts
                if all(abs(start - used_start) >= max_window_seconds for used_start in starts_used)
            ]
            used_count = len(candidate_starts) - len(available_starts)
            used_ratio = used_count / max(1, window_count)
            if used_ratio > 0.85 or not available_starts:
                exhausted_files.append(f"{source_key} ({used_ratio:.0%} used)")
                continue
            start_second = random.choice(available_starts)
            chosen = (remote, fname, local_full, duration, window_seconds, start_second, source_key, starts_used)
            break
        except Exception as exc:
            print(f"⚠️ Cloud source skipped; trying next source: {source_key}: {type(exc).__name__}: {exc}")
            exhausted_files.append(f"{source_key} (source error: {type(exc).__name__})")
            continue

    if chosen is None:
        details = "; ".join(exhausted_files[:5])
        raise RuntimeError(
            "No unused source windows up to 65 seconds remain in the cloud pool; "
            f"files are only exhausted after >85% of their candidate windows are used. {details}"
        )

    remote, fname, local_full, source_duration, window_seconds, start_second, source_key, starts_used = chosen
    local_clip = "/tmp/gta_source_window.mp4"
    if os.path.exists(local_clip):
        os.remove(local_clip)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start_second:.3f}", "-i", local_full,
            "-t", f"{window_seconds:.1f}", "-map", "0:v:0", "-map", "0:a?",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            local_clip
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=240
    )
    if not os.path.isfile(local_clip) or os.path.getsize(local_clip) < 100_000:
        raise RuntimeError(f"Could not extract selected {window_seconds:.1f}-second gameplay window from {fname}.")

    window_duration_text = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", local_clip
        ],
        text=True, stderr=subprocess.PIPE, timeout=60
    ).strip()
    window_duration = float(window_duration_text)
    if not (window_seconds - 1.0 <= window_duration <= window_seconds + 0.5):
        raise RuntimeError(f"Extracted gameplay window has invalid duration: {window_duration:.2f}s")

    source_hash = source_window_hash(source_key, start_second, window_seconds)
    uploaded_hashes = {
        entry.get("hash") for entry in uploaded_entries if entry.get("hash")
    }
    if source_hash in uploaded_hashes:
        raise RuntimeError(f"Duplicate {window_seconds:.0f}-second source window detected: {source_key} at {start_second:.0f}s")

    used_sources.append(f"{source_key}@{start_second:.0f}s")
    hist["used_sources"] = used_sources[-500:]
    print(
        f">> Fresh window selected: {source_key} at {start_second:.0f}s "
        f"({window_seconds:.0f}s window; source duration {source_duration:.1f}s; "
        f"{len(starts_used)} prior windows recorded)."
    )
    return fname, local_clip, source_hash, start_second, window_seconds, source_key

def _normalize_creator_script(script):
    """Replace stock AI-sounding phrases with plain spoken gamer wording."""
    replacements = (
        (r"\\bbreaking the internet\\b", "blowing up online"),
        (r"\\bin today's gaming landscape\\b", "in gaming right now"),
        (r"\\bwithout further ado\\b", "here's the thing"),
        (r"\\bin conclusion\\b", "so"),
        (r"\\bfurthermore\\b", "plus"),
        (r"\\bmoreover\\b", "and"),
        (r"\\bgame-changer\\b", "big shift"),
        (r"\\bdelve into\\b", "look at"),
        (r"\\bdelve\\b", "look"),
        (r"\\bunleash\\b", "show"),
        (r"\\brealm\\b", "world"),
        (r"\\byou won't believe\\b", "this is wild"),
    )
    normalized = str(script or "")
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return re.sub(r"\\s+", " ", normalized).strip()


def _parse_strict_ai_json(raw):
    cleaned = re.sub(r"^\s*\x60{3}(?:json)?\s*|\s*\x60{3}\s*$", "", str(raw).strip(), flags=re.IGNORECASE)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")
    required = ("hook", "script", "title", "comment", "creative_angle")
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in required):
        raise ValueError("AI JSON must contain non-empty hook, script, title, and comment strings")
    data["script"] = _normalize_creator_script(data["script"])
    words = re.findall(r"\b[\w’'-]+\b", data["script"])
    if not 35 <= len(words) <= 145:
        raise ValueError(f"narration must contain 35–145 words; received {len(words)}")
    opener = " ".join(words[:6]).lower()
    if re.match(r"^(?:in this video|have you ever wondered|today we|let me show you|welcome back|what if you)", opener):
        raise ValueError("opening six words are slow/filler; begin with the visible action or payoff")
    if len(words) < 6:
        raise ValueError("script needs at least six opening words")
    if not re.search(r"[.!?][\"')\]]?$", data["script"].strip()):
        raise ValueError("narration must end with a complete sentence")

    angle = str(data["creative_angle"]).strip().lower()
    if angle not in ("story_fact", "clip_focused"):
        raise ValueError("creative_angle must be story_fact or clip_focused")
    data["title"] = _repair_title(data["title"], "Gaming")
    title = data["title"].strip()
    generic_title = re.compile(
        r"\b(?:tracking leads through the city|from the beach|pushing physics|"
        r"gaming moments|epic gameplay|crazy gameplay|a day in|exploring the city)\b",
        re.IGNORECASE
    )
    curiosity_hook = re.compile(
        r"\b(?:\d+|secret|hidden|rarest|easter egg|why|how|never|actually|"
        r"still|vs\.?|beat|forgotten|only|impossible|mystery|truth|most)\b",
        re.IGNORECASE
    )
    if generic_title.search(title) or not curiosity_hook.search(title):
        data["title"] = _repair_title(title, "Gaming")
    return data

def _generate_text_fallback(prompt, provider):
    """Free text-only fallback when Gemini's visual endpoint is unavailable."""
    if provider == "groq":
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            return None
        response = None
        for model in _discover_groq_models(key):
            for attempt in range(3):
                try:
                    candidate = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8},
                        timeout=35
                    )
                    if candidate.status_code == 200:
                        response = candidate
                        break
                    print(f"Groq {model} attempt {attempt + 1}/3 HTTP {candidate.status_code}: {candidate.text[:120]}", flush=True)
                    if candidate.status_code not in (429, 500, 502, 503, 504):
                        break
                except requests.RequestException as exc:
                    print(f"Groq {model} attempt {attempt + 1}/3 network error: {exc}", flush=True)
                if attempt < 2:
                    time.sleep(2 ** attempt)
            if response is not None:
                break
        if response is None:
            return None
    elif provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            return None
        response = None
        for model in ("qwen/qwen-2.5-72b-instruct:free", "deepseek/deepseek-chat:free",
                      "meta-llama/llama-3.3-70b-instruct:free"):
            try:
                candidate = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8},
                    timeout=35
                )
                if candidate.status_code == 200:
                    response = candidate
                    break
            except requests.RequestException:
                continue
        if response is None:
            return None
    else:
        return None
    if response.status_code != 200:
        print(f"{provider} fallback HTTP {response.status_code}: {response.text[:160]}")
        return None
    return response.json()["choices"][0]["message"]["content"].strip()


def analyze_clip_and_generate_package(fname, local_clip, hist, focus):
    """Use sampled frames from the actual source clip; fail closed if visual analysis is unavailable."""
    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    duration_text = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", local_clip],
        text=True, timeout=30
    ).strip()
    duration = max(1.0, float(duration_text))
    frame_paths = []
    # Prefer a strict visual match, but always fall back to the best available window.
    ranked_openings = _render_engine._score_motion_windows(local_clip, duration, 2.2)
    first_action_start, opening_metrics = _render_engine.select_opening_window(
        local_clip, ranked_openings, 2.2, label="visual-analysis"
    )
    sample_times = [
        first_action_start + 0.35,
        first_action_start + 1.25,
        first_action_start + 2.45,
        min(max(0.0, duration * 0.88), max(0.0, duration - 0.1)),
    ]
    for index, timestamp in enumerate(sample_times, start=1):
        frame_path = f"/tmp/gameplay_frame_{index}.jpg"
        timestamp = min(max(0.0, timestamp), max(0.0, duration - 0.1))
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
    recent_creative = [x for x in hist.get("recent_creative_entries", []) if isinstance(x, dict)][-10:]
    recent_title_hooks = "\n".join(
        "- Title: " + str(x.get("title", "")) + " | Opening: " + str(x.get("hook", "")) + " | Angle: " + str(x.get("angle", ""))
        for x in recent_creative
    ) or "(no previous title/hook records)"
    previous_angle = recent_creative[-1].get("angle", "") if recent_creative else ""
    winning_examples = hist.get("winning_examples") or []
    winning_examples_text = json.dumps(winning_examples[:3], ensure_ascii=False)
    hype_now = fetch_live_hype_context()
    current_utc_date = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    fact_guardrails = (
        "2026 VERIFIED GTA VI FACT LOCK (checked 2026-11-26): Grand Theft Auto VI launched on "
        "November 19, 2026 for PlayStation 5 and Xbox Series X|S. Rockstar/Take-Two have not announced "
        "a PC version or PC release date as of the check date. Never claim GTA VI is already released "
        "on PC, invent a PC date, or describe it as an upcoming unreleased game. If a PC-port rumor is "
        "relevant, label it unconfirmed and do not present it as company news. If the current date is "
        "later than the fact-check date, avoid making a fresh PC-status claim unless a current official "
        "Rockstar or Take-Two source is supplied. Separate confirmed facts from rumors for every game."
    )
    prompt = (
        "Adaptive US gaming Shorts creator: inspect all four gameplay frames in timestamp order and filename context first. "
        f"Current UTC date: {current_utc_date}. Fact guardrails: {fact_guardrails} "
        "Choose creative_angle exactly story_fact or clip_focused. For energetic free-roam, chases, stunts, and crashes, "
        "choose story_fact: let the action hold attention while narration tells an accurate gaming story, developer detail, "
        "or surprising fact; narration need not describe driving. For a specific experiment, object, NPC behavior, glitch, "
        "physics test, secret, or Easter egg, choose clip_focused and narrate the visible setup through its exact payoff. "
        "Never invent what the frames show or make unsupported insider claims. "
        "Write naturally between 35 and 145 spoken words, targeting a finished voiceover of 14.0-58.5 seconds. Use as many or as few words as the story genuinely needs; never pad or force a fixed word count. Sound like a sharp US gaming creator speaking to a friend: contractions, casual gamer vocabulary, short fragments mixed with a few longer sentences, specific observations, and natural emphasis. Avoid formal transitions and generic hype. BANNED CLICHES: delve, unleash, realm, breaking the internet, in today's gaming landscape, game-changer, without further ado, in conclusion, furthermore, moreover, 'you won't believe'. Do not use them. The FIRST SIX WORDS must be a concrete curiosity hook tied to the strongest visible action. Start with the object/action/payoff itself, never filler such as In this video, Have you ever wondered, Today we, or Let me show you. Build a clear setup, escalation, and specific payoff. The FINAL FIVE WORDS must form a grammatical bridge into the opening six words when the video loops; read the ending and opening consecutively to check the sentence flows naturally. Avoid a fake cliffhanger or repeating the hook verbatim. "
        f"Filename: {clean_name}. Focus: {focus}. Current trend context: {hype_now}. Previous angle: {previous_angle}. "
        f"Channel's measured winning examples (titles/hooks/angles; use as evidence, do not copy): {winning_examples_text}. "
        f"Recent scripts to avoid:\\n{recent_avoid}\\n"
        f"Last 10 titles and opening hooks (avoid topic, wording, sentence shape, and hook pattern):\\n{recent_title_hooks}\\n"
        "Never repeat the same topic angle or hook pattern twice in a row. Vary openings: mystery, challenge, "
        "counterintuitive fact, surprising claim, or a specific visual question. "
        "Return ONLY JSON keys creative_angle, hook, script, title, comment, ig_caption, tags. "
        "hook: 3-5 punchy words for the first-frame badge. title: under 70 characters, truthful, high-curiosity, "
        "grounded in the game/frames; avoid generic titles and unsupported secrets. "
        "comment: one short natural debate/curiosity question tied to this video. No spam. "
        "ig_caption short; tags array. No markdown fences."
    )
    parts = [{"text": prompt}]
    for path in frame_paths:
        with open(path, "rb") as image_file:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_file.read()).decode("ascii")}})
    errors, data = [], None
    if gem_key:
        model, raw = _gemini_generate(
            gem_key, parts,
            {"temperature": 0.8, "responseMimeType": "application/json"}
        )
        if raw:
            try:
                candidate = _parse_strict_ai_json(raw)
                from difflib import SequenceMatcher
                normalized = re.sub(r"[^a-z0-9 ]", "", candidate["script"].lower())
                if any(SequenceMatcher(None, normalized, re.sub(r"[^a-z0-9 ]", "", old.lower())).ratio() >= 0.78 for old in recent_scripts if old):
                    errors.append(f"{model}: narration too similar to a recent script")
                else:
                    data = candidate
                    print(f">> Adaptive narration generated by discovered Gemini model {model}; sampled 4 frames.")
                    print(f"[narration] {candidate['script']}")
            except Exception as exc:
                errors.append(f"{model}: {type(exc).__name__}: {exc}")

    if data is None:
        # Gemini has exhausted every discovered Flash/Pro model and its retries.
        # Now try every active Groq model with three attempts each, using measured
        # action timestamps as evidence; never fabricate unseen events.
        action_windows = _render_engine._score_motion_windows(local_clip, duration, 2.2)[:5]
        action_evidence = ", ".join(f"{stamp:.1f}s" for stamp in action_windows)
        fallback_prompt = (
            prompt + "\nGemini visual generation failed after model discovery and retries. "
            f"Measured high-motion gameplay windows occur at source timestamps: {action_evidence}. "
            "You are text-only: do not invent what happens in those windows or describe unseen objects, rooms, characters, or events. "
            "Use only the supplied filename, focus, reliable game facts, and timestamp evidence. "
            "If a specific truthful action beat cannot be stated, do not return generic filler. "
            "Return the same strict JSON schema; keep narration naturally between 35 and 145 spoken words (14-58.5 seconds), with no fixed-length target."
        )
        for provider in ("groq", "openrouter"):
            try:
                fallback_raw = _generate_text_fallback(fallback_prompt, provider)
                if not fallback_raw:
                    continue
                candidate = _parse_strict_ai_json(fallback_raw)
                from difflib import SequenceMatcher
                normalized = re.sub(r"[^a-z0-9 ]", "", candidate["script"].lower())
                if any(SequenceMatcher(None, normalized, re.sub(r"[^a-z0-9 ]", "", old.lower())).ratio() >= 0.78 for old in recent_scripts if old):
                    errors.append(f"{provider}: fallback narration too similar to a recent script")
                    continue
                data = candidate
                print(f">> Adaptive narration generated by {provider} action-evidence text fallback.")
                break
            except Exception as exc:
                errors.append(f"{provider}: {type(exc).__name__}: {exc}")

    if data is None:
        raise RuntimeError("All Gemini and Groq/OpenRouter attempts failed; refusing to publish generic offline narration. " + "; ".join(errors[-8:]))
    data["title"] = _repair_title(data.get("title", ""), "Gaming")
    title = _repair_title(data["title"], "Gaming")
    hook = data["hook"].replace("'", "").replace('"', "").strip()
    script = data["script"].strip()
    comment = data["comment"].strip()
    angle = data["creative_angle"].strip().lower()
    creative_history = hist.setdefault("recent_creative_entries", [])
    creative_history.append({"title": title, "hook": hook, "angle": angle,
                             "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    hist["recent_creative_entries"] = creative_history[-30:]
    history = hist.setdefault("recent_scripts", [])
    history.append({"source": fname, "script": script, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    hist["recent_scripts"] = history[-30:]
    hist.setdefault("used_topics", []).append(hook)
    caption = data.get("ig_caption") or f"{title} Follow for daily gaming secrets! #gaming #shorts"
    tags = data.get("tags") or ["Gaming", "Shorts"]
    if not isinstance(tags, list):
        tags = ["Gaming", "Shorts"]
    return title, hook, script, comment, caption, tags, angle

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
        "[0:v]setpts=0.95*PTS,scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,setsar=1,"
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

    # The videos.insert response requested part="snippet,status" and normally
    # includes the accepted privacy status. Use that as the first verification
    # source; videos.list may be unavailable when OAuth lacks youtube.readonly.
    privacy_status = (resp or {}).get("status", {}).get("privacyStatus", "UNKNOWN")
    privacy_check_detail = ""
    try:
        status_response = youtube.videos().list(part="status", id=vid_id).execute()
        items = status_response.get("items", [])
        if items:
            privacy_status = items[0].get("status", {}).get("privacyStatus", privacy_status)
        elif privacy_status == "UNKNOWN":
            privacy_check_detail = "videos.list returned no item and videos.insert omitted privacy status"
    except Exception as exc:
        privacy_check_detail = _youtube_error_details(exc)
        print(
            f"YouTube readback unavailable ({privacy_check_detail}); "
            f"using videos.insert response privacyStatus={privacy_status}"
        )

    hist.setdefault("uploaded_source_windows", []).append({
        "hash": source_hash, "source": source_filename,
        "start_second": float(start_second), "duration": float(source_duration),
        "video_id": vid_id,
        "privacy_status": privacy_status,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    hist["uploaded_source_windows"] = hist["uploaded_source_windows"][-500:]
    used_window_records = hist.setdefault("used_source_windows", [])
    used_window_records.append({"source": source_filename, "start_second": float(start_second),
                                "duration": float(source_duration), "hash": source_hash,
                                "video_id": vid_id})
    hist["used_source_windows"] = used_window_records[-500:]
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
    privacy_permission_denied = bool(
        privacy_check_detail and re.search(r"\b403\b|insufficientPermissions", privacy_check_detail, re.I)
    )
    comment_permission_denied = bool(
        re.search(r"\b403\b|insufficientPermissions", comment_status, re.I)
    )
    if privacy_check_detail and not privacy_permission_denied:
        privacy_line += f"\nPrivacy verification error: {privacy_check_detail}"
    summary_lines = [
        "✅ YouTube upload succeeded!",
        f"Title: {title}",
        f"YouTube: https://youtube.com/shorts/{vid_id}",
        privacy_line,
    ]
    if comment_status and not comment_permission_denied:
        summary_lines.append(f"YouTube first comment: {comment_status}")
    summary_lines.append(f"Instagram Reels: {ig_status}")
    summary = "\n".join(summary_lines)
    if privacy_permission_denied:
        print("YouTube privacy verification skipped in Telegram summary (HTTP 403 insufficientPermissions).", flush=True)
    if comment_permission_denied:
        print("YouTube first comment skipped in Telegram summary (HTTP 403 insufficientPermissions).", flush=True)
    deliver_to_telegram(summary, "final.mp4", ig_caption)
    return vid_id

if __name__ == "__main__":
    try:
        hist = json.load(open("history.json")) if os.path.exists("history.json") else {"used_windows": [], "used_topics": []}
        cfg = json.load(open("config.json")) if os.path.exists("config.json") else {"focus": "auto", "last_video_id": "", "pending_url": ""}
        focus = cfg.get("focus", "auto")
        try:
            from analytics_tuner import tune_daily_analytics
            tune_daily_analytics(cfg, hist)
            with open("config.json", "w", encoding="utf-8") as config_file:
                json.dump(cfg, config_file, indent=2)
        except Exception as analytics_error:
            print(f"[analytics] Non-fatal tuner error: {type(analytics_error).__name__}: {analytics_error}")
        hist["winning_examples"] = cfg.get("winning_examples", [])
        fname, local_clip, source_hash, start_second, source_duration, source_key = stream_unique_action_clips(hist, focus)
        title, top_hook, script, first_comment, ig_caption, tags, creative_angle = generate_viral_package(fname, hist, focus, local_clip)
        rendered_path = render_full_bleed_short(local_clip, script, "final.mp4", top_hook=top_hook, creative_angle=creative_angle)
        if not os.path.isfile(rendered_path) or os.path.getsize(rendered_path) < 100_000:
            raise RuntimeError("Render step returned without a valid final video.")
        final_duration = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", rendered_path],
            text=True, timeout=60
        ).strip())
        if not (14.0 <= final_duration <= 58.5):
            raise RuntimeError(
                f"Rendered Short must be 14.0–58.5 seconds; got {final_duration:.2f}s. Refusing to publish."
            )
        uploaded_video_id = publish_everywhere(title, script, first_comment, ig_caption, tags, cfg, hist, source_hash, source_key, start_second, source_duration)
        if hist.get("recent_creative_entries"):
            hist["recent_creative_entries"][-1]["video_id"] = uploaded_video_id
            hist["recent_creative_entries"][-1]["source_key"] = source_key
        with open("history.json", "w", encoding="utf-8") as history_file:
            json.dump({"used_windows": hist.get("used_windows", [])[-400:],
                       "used_topics": hist.get("used_topics", [])[-100:],
                       "recent_scripts": hist.get("recent_scripts", [])[-30:],
                       "recent_creative_entries": hist.get("recent_creative_entries", [])[-30:],
                       "used_sources": hist.get("used_sources", [])[-100:],
                       "uploaded_source_windows": hist.get("uploaded_source_windows", [])[-500:],
                       "used_source_windows": hist.get("used_source_windows", [])[-500:],
                       "published_source_files": hist.get("published_source_files", [])[-1000:]},
                      history_file, indent=2)
        with open("config.json", "w", encoding="utf-8") as config_file:
            json.dump(cfg, config_file, indent=2)
    except Exception as e:
        deliver_to_telegram(f"⚠️ Pipeline Alert: {e}")
        raise
