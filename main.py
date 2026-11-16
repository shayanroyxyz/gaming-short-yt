import os
import re
import json
import glob
import random
import asyncio
import datetime
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai

WORK = "/tmp/build"
VOICE = "en-US-AndrewMultilingualNeural"
DRY_RUN = os.environ.get("DRY_RUN") == "1"

GAMES = [
    {
        "name": "GTA 6",
        "channel": "https://www.youtube.com/@RockstarGames/videos",
        "tags": ["GTA6", "GTAVI", "ViceCity", "GTA6Trailer", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "GTA 6 Details You Missed in the Trailer! #shorts",
            "hook": "Three insane GTA 6 details that completely change Vice City.",
            "clips": [
                "First, look closely at the water physics. Every ripple reacts to the boat wake perfectly.",
                "Second, the NPC crowd density in the beach scene is triple what GTA 5 could handle.",
                "And third, the traffic light timing in downtown Vice City is actually realistic."
            ]
        }
    },
    {
        "name": "GTA 5",
        "channel": "https://www.youtube.com/@NoCopyrightGameplays/videos",
        "tags": ["GTA5", "GTAMyths", "GTA5Gameplay", "Shorts"],
        "fallback_script": {
            "title": "3 Insane GTA 5 Moments That Broke Physics! #shorts",
            "hook": "Watch these three crazy GTA 5 moments that broke the game engine.",
            "clips": [
                "First, look at how the ragdoll physics react when launching off Mount Chiliad.",
                "Second, watch what happens when NPC traffic glitches during a five-star chase.",
                "And third, this pilot threads a jet through the tightest tunnel on the map."
            ]
        }
    },
    {
        "name": "Minecraft",
        "channel": "https://www.youtube.com/@OrbiGameplay/videos",
        "tags": ["Minecraft", "MinecraftFacts", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "3 Insane Minecraft Clutches! #shorts",
            "hook": "You won't believe these rare Minecraft gameplay moments.",
            "clips": [
                "First, a frame-perfect water bucket clutch that saves a hardcore world.",
                "Second, creepers panicking and sprinting away the second a cat appears.",
                "And third, redstone TNT cannons launching a player thousands of blocks."
            ]
        }
    }
]

GAME_WEIGHTS = [0.7, 0.2, 0.1] 

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

def setup_cookies():
    ig_path, x_path = None, None
    if os.environ.get("IG_COOKIES", "").strip():
        ig_path = "/tmp/ig_cookies.txt"
        open(ig_path, "w").write(os.environ["IG_COOKIES"])
    if os.environ.get("X_COOKIES", "").strip():
        x_path = "/tmp/x_cookies.txt"
        open(x_path, "w").write(os.environ["X_COOKIES"])
    return ig_path, x_path

def download_youtube_fallback(game):
    output_path = os.path.join(WORK, "source.mp4")
    log(f"Downloading gameplay for {game['name']}...")
    cmd = ["yt-dlp", "--impersonate", "chrome", "--playlist-end", "3", "--match-filter", "duration > 30 & !is_live", "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "-o", output_path, game["channel"]]
    try:
        subprocess.run(cmd, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if valid_video(output_path): return output_path
    except: pass
    return None

def slice_video(src, start_time, duration, out_path):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start_time), "-i", src, "-t", str(duration), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", out_path]
    subprocess.run(cmd, check=True)
    return out_path

def generate_script(game):
    log(f"Generating viral script for {game['name']}...")
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        # Enforced #shorts in the prompt to fix the 0 views issue
        prompt = f"Write a fast-paced 3-clip YouTube Shorts script for {game['name']}. Return strict JSON: {{\"title\": \"<100 chars, clickbait, MUST end with #shorts>\", \"hook\": \"one sentence high-retention hook\", \"clips\": [\"clip 1\", \"clip 2\", \"clip 3\"]}}. The text must be spoken by a narrator. Do not use emojis."
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return json.loads(res.text[res.text.find("{"):res.text.rfind("}")+1])
    except Exception as e:
        log(f"LLM failed, using fallback: {e}")
        return game["fallback_script"]

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

def upload(path, title, tags):
    if DRY_RUN: return
    creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title[:100], "description": "Subscribe for daily clips! #gta6 #vicecity", "tags": tags, "categoryId": "20"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=1024*1024*5, resumable=True)
    yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    log("Uploaded successfully!")

def main():
    os.makedirs(WORK, exist_ok=True)
    game = random.choices(GAMES, weights=GAME_WEIGHTS, k=1)[0]
    log(f"Selected Game for this run: {game['name']}")
    
    src = download_youtube_fallback(game)
    if not src:
        log("No source video found. Aborting.")
        return

    script = generate_script(game)
    full_text = script["hook"] + " " + " ".join(script["clips"])
    audio_path = synthesize(full_text, os.path.join(WORK, "voice.mp3"))
    
    segments = []
    for i in range(3):
        seg_path = os.path.join(WORK, f"seg_{i}.mp4")
        start = random.randint(0, max(1, int(get_duration(src)) - 15))
        slice_video(src, start, 12, seg_path)
        segments.append(seg_path)
        
    concat_txt = os.path.join(WORK, "concat.txt")
    with open(concat_txt, "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
        
    joined = os.path.join(WORK, "joined.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", joined], check=True)
    
    ass_path = os.path.join(WORK, "subs.ass")
    build_ass([script["hook"]] + script["clips"], ass_path)
    
    final_path = os.path.join(WORK, "final.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined, "-i", audio_path, "-vf", "ass=subs.ass", "-c:v", "libx264", "-c:a", "aac", "-shortest", final_path], check=True, cwd=WORK)
    
    upload(final_path, script["title"], game["tags"])

if __name__ == "__main__":
    main()
