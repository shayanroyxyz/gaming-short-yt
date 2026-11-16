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

DEFAULT_GTA = {
    "name": "GTA 6",
    "channel": "https://www.youtube.com/@RockstarGames/videos",
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
}

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

def download_video(url):
    output_path = os.path.join(WORK, "source.mp4")
    log(f"Downloading from URL: {url}")
    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=web;getpot_bgutil_baseurl=http://127.0.0.1:4416",
        "--download-sections", "*0:00-4:00",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "-o", output_path,
        url
    ]
    try:
        subprocess.run(cmd, check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if valid_video(output_path): return output_path
    except Exception as e:
        log(f"Download failed or timed out: {e}")
    return None

def safe_auto_edit_and_slice(src):
    log("Running Auto-Editor to cut dead space...")
    edited_path = os.path.join(WORK, "edited_source.mp4")
    cmd_edit = ["auto-editor", src, "--edit", "audio:threshold=0.04", "--margin", "0.2sec", "-o", edited_path]
    try:
        subprocess.run(cmd_edit, check=True, timeout=120)
    except Exception as e:
        log(f"Auto-editor failed, using original: {e}")
        edited_path = src

    log("Slicing 3 segments...")
    segments = []
    for i in range(3):
        seg_path = os.path.join(WORK, f"seg_{i}.mp4")
        start = random.randint(0, max(1, int(get_duration(edited_path)) - 15))
        cmd_slice = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", edited_path, "-t", "12", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", seg_path]
        subprocess.run(cmd_slice, check=True)
        segments.append(seg_path)
    return segments

# --- THE 3-TIER AI CASCADE ---
def call_gemini(prompt):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: return None
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return res.text
    except Exception as e:
        log(f"Gemini failed (Limit reached?): {e}")
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

def call_groq(prompt):
    try:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key: return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8, "response_format": {"type": "json_object"}}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content']
    except Exception as e:
        log(f"Groq failed: {e}")
        return None

def generate_script(game_name, rules=""):
    log(f"Generating VIRAL Script for {game_name}...")
    
    prompt = f"""
    You are a top-tier YouTube Shorts viral strategist. Write a script for {game_name}.
    CRITICAL CAMPAIGN RULES: {rules}
    
    ALGORITHM TRICKS YOU MUST USE:
    1. The Hook must create a Curiosity Gap (e.g., "This changes everything...").
    2. The last sentence of clip 3 MUST seamlessly loop back to the hook.
    3. Use high-energy American gaming slang.
    
    Return ONLY a valid JSON object. Do not use markdown. Format: 
    {{
        "title": "<Max 80 chars. Extreme clickbait. MUST end with #shorts and any required tags>",
        "description": "<2 sentences with SEO keywords and 5 hashtags. Include required links/info>",
        "hook": "<The curiosity gap sentence>",
        "clips": ["<clip 1: deep dive>", "<clip 2: more context>", "<clip 3: the loop closer>"]
    }}
    """
    
    # The Cascade: Try Gemini -> Pollinations -> Groq
    response_text = call_gemini(prompt)
    if not response_text:
        log("Switching to Pollinations backup...")
        response_text = call_pollinations(prompt)
    if not response_text:
        log("Switching to Groq backup...")
        response_text = call_groq(prompt)
    
    if not response_text:
        log("All AI brains failed. Using fallback script.")
        return DEFAULT_GTA["fallback_script"]

    try:
        # Extract JSON safely
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        data = json.loads(response_text[start:end])
        return data
    except Exception as e:
        log(f"Failed to parse AI JSON: {e}. Using fallback.")
        return DEFAULT_GTA["fallback_script"]

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
    
    publish_time = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "20"}, 
        "status": {"privacyStatus": "private", "publishAt": publish_time, "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=1024*1024*5, resumable=True)
    yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    log(f"Successfully scheduled for US Peak: {title}")

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
        url, game, rules = manual_url, manual_game or "Gaming", manual_rules
    elif json_url:
        log("JSON CAMPAIGN MODE ACTIVATED")
        url, game, rules = json_url, json_game, json_rules
    else:
        log("AUTO MODE: Defaulting to GTA 6")
        url, game, rules = DEFAULT_GTA["channel"], DEFAULT_GTA["name"], ""

    src = download_video(url)
    if not src:
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
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-i", audio_path, "-vf", "ass=subs.ass", "-c:v", "libx264", "-c:a", "aac", "-shortest", final_path], check=True, cwd=WORK)
    
    upload(final_path, script["title"], script["description"], ["gaming", "shorts", game])

if __name__ == "__main__":
    main()
