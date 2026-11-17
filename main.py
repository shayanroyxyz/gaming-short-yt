import os
import re
import json
import random
import asyncio
import datetime
import subprocess
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
import edge_tts

WORK = "/tmp/build"
VOICE = "en-US-AndrewMultilingualNeural"
DRY_RUN = os.environ.get("DRY_RUN") == "1"

# --- ROBUST GAME SOURCES ---
# Using ytsearch5: to get top results instead of a single specific query
GAMES = [
    {
        "name": "GTA V",
        "search_query": "ytsearch5:GTA 5 gameplay 4k no commentary",
        "fallback_url": "https://www.youtube.com/watch?v=QkkoHAzjnUs", # Safe GTA V clip
        "tags": ["GTA 5", "GTAV", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "GTA 5 Secrets You Never Noticed! #shorts",
            "description": "Subscribe for daily GTA content! #gta5 #gaming #shorts",
            "hook": "These three GTA 5 details completely change how you play.",
            "clips": [
                "First, look at the water physics. Every ripple reacts perfectly to the boat wake.",
                "Second, the NPC density on the beach is triple what you see on console.",
                "And third, the traffic lights downtown actually sync up realistically."
            ]
        }
    },
    {
        "name": "GTA 6 Trailer",
        "search_query": "ytsearch5:GTA 6 trailer 4k",
        "fallback_url": "https://www.youtube.com/watch?v=QdBZY2fkU-0", # Official Trailer 1
        "tags": ["GTA 6", "GTA VI", "Vice City", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "The GTA 6 Detail That Changes EVERYTHING! #shorts",
            "description": "Subscribe for daily GTA 6 news! #gta6 #vicecity #gaming #shorts",
            "hook": "This one GTA 6 mechanic completely breaks everything we knew about Rockstar games.",
            "clips": [
                "Look at the water physics in the trailer. Every ripple reacts perfectly to the boat wake.",
                "Now look at the NPC density on the beach. It is triple what GTA 5 could handle.",
                "And the traffic lights downtown actually sync up realistically. This game is insane."
            ]
        }
    },
    {
        "name": "Minecraft",
        "search_query": "ytsearch5:Minecraft parkour gameplay 4k no commentary",
        "fallback_url": "https://www.youtube.com/watch?v=1V8Xp5n8Q1E",
        "tags": ["Minecraft", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "Insane Minecraft Clutches! #shorts",
            "description": "Subscribe for daily gaming shorts! #minecraft #gaming #shorts",
            "hook": "You won't believe these rare Minecraft gameplay moments.",
            "clips": [
                "First, a frame-perfect water bucket clutch that saves a hardcore world.",
                "Second, creepers panicking and sprinting away the second a cat appears.",
                "And third, redstone TNT cannons launching a player thousands of blocks."
            ]
        }
    }
]

GAME_WEIGHTS = [0.5, 0.3, 0.2] # 50% GTA 5, 30% GTA 6 Trailer, 20% Minecraft

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_duration(path):
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]).decode().strip()
        return float(out)
    except: return 0.0

def valid_video(path):
    if not os.path.exists(path) or os.path.getsize(path) < 350_000: return False
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path]).decode().strip()
        w, h = map(int, out.split("x"))
        return min(w, h) >= 360 and get_duration(path) >= 5.0
    except: return False

def download_video(game):
    output_path = os.path.join(WORK, "source.mp4")
    log(f"Searching and downloading: {game['search_query']}")
    
    # FIX: Removed strict match filters, added ignore-errors, limited to 3 minutes
    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=web;getpot_bgutil_baseurl=http://127.0.0.1:4416",
        "--playlist-end", "1",
        "--download-sections", "*0:00-3:00",
        "--ignore-errors",
        "--no-warnings",
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]",
        "-o", output_path,
        game["search_query"]
    ]
    try:
        subprocess.run(cmd, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if valid_video(output_path): return output_path
    except Exception as e:
        log(f"Search download failed: {e}. Trying direct fallback URL...")
        # FALLBACK: If search fails, use the direct URL
        cmd[cmd.index(game["search_query"])] = game["fallback_url"]
        try:
            subprocess.run(cmd, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if valid_video(output_path): return output_path
        except Exception as e2:
            log(f"Fallback URL also failed: {e2}")
    return None

# --- PROFESSIONAL AUTO-EDITOR ---
def safe_auto_edit_and_slice(src):
    log("Running Auto-Editor to cut dead space...")
    edited_path = os.path.join(WORK, "edited_source.mp4")
    # auto-editor removes silence based on audio threshold
    cmd_edit = ["auto-editor", src, "--edit", "audio:threshold=0.04", "--margin", "0.2sec", "-o", edited_path]
    try:
        subprocess.run(cmd_edit, check=True, timeout=120)
    except Exception as e:
        log(f"Auto-editor failed, using original: {e}")
        edited_path = src

    log("Slicing 3 segments with Professional Filters (Audio Normalization, Dynamic Zoom)...")
    segments = []
    for i in range(3):
        seg_path = os.path.join(WORK, f"seg_{i}.mp4")
        start = random.randint(0, max(1, int(get_duration(edited_path)) - 15))
        
        # Visual: Dynamic Zoom, Random Horizontal Flip for Content ID bypass
        visual_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        visual_filter += ",zoompan=z='min(zoom+0.0015,1.5)':d=1:s=1080x1920" # Slow zoom effect
        if random.choice([True, False]):
            visual_filter += ",hflip"
        
        # Audio: Normalize volume, remove background hiss (if any)
        audio_filter = "loudnorm=I=-14:TP=-1.5:LRA=11,highpass=f=80,lowpass=f=12000"

        cmd_slice = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(start), "-i", edited_path, "-t", "12",
            "-vf", visual_filter,
            "-af", audio_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            seg_path
        ]
        subprocess.run(cmd_slice, check=True)
        segments.append(seg_path)
    return segments

# --- UNLIMITED AI CASCADE ---
def call_gemini(prompt):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return None
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return res.text
    except Exception as e:
        log(f"Gemini failed: {e}")
        return None

def call_pollinations(prompt):
    try:
        url = "https://text.pollinations.ai/openai"
        headers = {"Content-Type": "application/json"}
        payload = {"model": "openai", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content']
    except Exception as e:
        log(f"Pollinations failed: {e}")
        return None

def call_keyless_ai(prompt):
    # Unlimited free OpenAI-compatible endpoint
    try:
        url = "https://keylessai.thryx.workers.dev/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content']
    except Exception as e:
        log(f"KeylessAI failed: {e}")
        return None

def generate_script(game_name, rules=""):
    log(f"Generating VIRAL Script for {game_name}...")
    prompt = f"""
    Write a YouTube Shorts script for {game_name}. RULES: {rules}
    Make the Hook a Curiosity Gap. Make the end loop to the beginning. Use gamer slang.
    Return ONLY valid JSON: 
    {{
        "title": "<Max 80 chars. Clickbait. MUST end with #shorts>",
        "description": "<2 sentences with SEO keywords and 5 hashtags>",
        "hook": "<The curiosity gap sentence>",
        "clips": ["<clip 1>", "<clip 2>", "<clip 3: loop closer>"]
    }}
    """
    
    response_text = call_gemini(prompt)
    if not response_text:
        log("Switching to Pollinations (Unlimited)...")
        response_text = call_pollinations(prompt)
    if not response_text:
        log("Switching to KeylessAI (Unlimited)...")
        response_text = call_keyless_ai(prompt)
    
    if not response_text:
        log("All AI brains failed. Using fallback script.")
        return GAMES[0]["fallback_script"]

    try:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        return json.loads(response_text[start:end])
    except Exception as e:
        log(f"Failed to parse AI JSON: {e}. Using fallback.")
        return GAMES[0]["fallback_script"]

async def tts_async(text, out):
    comm = edge_tts.Communicate(text, VOICE, rate="+8%", pitch="-2Hz")
    await comm.save(out)

def synthesize(text, out_path):
    try: asyncio.run(tts_async(text, out_path))
    except:
        from gtts import gTTS
        gTTS(text=text, lang='en').save(out_path)
    return out_path

def build_ass(lines, out_path):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,84,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,3,5,50,50,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(out_path, "w") as f:
        f.write(header)
        for i, line in enumerate(lines):
            start = i * 12; end = start + 12
            f.write(f"Dialogue: 0,0:00:{start:02d}.00,0:00:{end:02d}.00,Default,,0,0,0,,{line}\n")

def upload(path, title, description, tags):
    if DRY_RUN: return
    creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds)
    
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "20"}, 
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=1024*1024*5, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = req.execute()
    log(f"✅ SUCCESSFULLY UPLOADED TO YOUTUBE! Video ID: {response['id']}")

def main():
    os.makedirs(WORK, exist_ok=True)
    
    manual_url = os.environ.get("CAMPAIGN_URL", "").strip()
    manual_game = os.environ.get("GAME_OVERRIDE", "").strip()
    manual_rules = os.environ.get("GUIDELINES", "").strip()
    
    json_url, json_game, json_rules = None, None, None
    if not manual_url and os.path.exists("campaigns.json"):
        try:
            with open("campaigns.json", "r") as f:
                campaigns = json.load(f)
                active_campaigns = [c for c in campaigns if c.get("active")]
                if active_campaigns:
                    chosen = random.choice(active_campaigns)
                    json_url = chosen.get("video_url")
                    json_game = chosen.get("game")
                    json_rules = chosen.get("rules", "")
                    log("RANDOMIZED MODE: Picked campaign from JSON.")
        except Exception as e:
            log(f"Failed to read campaigns.json: {e}")

    if manual_url:
        log("MANUAL MODE ACTIVATED")
        # If manual URL is provided, download directly (no search)
        src = os.path.join(WORK, "source.mp4")
        subprocess.run(["yt-dlp", "--extractor-args", "youtube:player_client=web;getpot_bgutil_baseurl=http://127.0.0.1:4416", "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "-o", src, manual_url], check=True)
        game, rules = manual_game or "Gaming", manual_rules
    elif json_url:
        log("JSON CAMPAIGN MODE ACTIVATED")
        src = os.path.join(WORK, "source.mp4")
        subprocess.run(["yt-dlp", "--extractor-args", "youtube:player_client=web;getpot_bgutil_baseurl=http://127.0.0.1:4416", "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "-o", src, json_url], check=True)
        game, rules = json_game, json_rules
    else:
        selected_game = random.choices(GAMES, weights=GAME_WEIGHTS, k=1)[0]
        log(f"AUTO MODE: Selected {selected_game['name']} based on dynamic rotation.")
        src = download_video(selected_game)
        game, rules = selected_game["name"], ""

    if not src or not os.path.exists(src):
        log("No source video found. Aborting.")
        return

    script = generate_script(game, rules)
    segments = safe_auto_edit_and_slice(src)
    
    full_text = script["hook"] + " " + " ".join(script["clips"])
    audio_path = synthesize(full_text, os.path.join(WORK, "voice.mp3"))
    
    concat_txt = os.path.join(WORK, "concat.txt")
    with open(concat_txt, "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
        
    joined = os.path.join(WORK, "joined.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", joined], check=True)
    
    ass_path = os.path.join(WORK, "subs.ass")
    build_ass([script["hook"]] + script["clips"], ass_path)
    
    final_path = os.path.join(WORK, "final.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-i", audio_path, "-vf", "ass=subs.ass", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", "-shortest", final_path], check=True, cwd=WORK)
    
    upload(final_path, script["title"], script["description"], ["gaming", "shorts", game])

if __name__ == "__main__":
    main()
