import os
import re
import json
import glob
import random
import asyncio
import datetime
import subprocess
import urllib.request
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai

try:
    from analyzer import analyze_channel_algorithm
except ImportError:
    def analyze_channel_algorithm():
        return {"best_games": ["Minecraft", "GTA 5", "Roblox"], "hours_since_last": 99.0, "allow_upload": True, "batch_size": 2, "report": "No analyzer"}

WORK = "/tmp/build"
VOICE = "en-US-AndrewMultilingualNeural"
DRY_RUN = os.environ.get("DRY_RUN") == "1"

GAMES = [
    {
        "name": "Minecraft",
        "channel": "https://www.youtube.com/@OrbiGameplay/videos",
        "tags": ["Minecraft", "MinecraftFacts", "Gaming", "Shorts"],
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
        "name": "GTA 5",
        "channel": "https://www.youtube.com/@NoCopyrightGameplays/videos",
        "tags": ["GTA5", "GTAMyths", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "3 Insane GTA 5 Clips You Need To See! #shorts",
            "hook": "Watch these three insane GTA 5 moments that broke game physics.",
            "clips": [
                "First up, look at how the ragdoll physics react when launching off Mount Chiliad at full speed... completely unreal.",
                "Second, watch what happens when NPC traffic glitches out during a five-star police chase in downtown Los Santos.",
                "And third, this stunt pilot threads a jet straight through the tightest tunnel on the map without a scratch."
            ]
        }
    }
]

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_duration(path):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ]).decode().strip()
        return float(out)
    except:
        return 0.0

def valid_gameplay_video(path):
    if not os.path.exists(path) or os.path.getsize(path) < 350_000:
        return False
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path
        ]).decode().strip()
        w, h = map(int, out.split("x"))
        # FIX: Added missing return statement and except block
        return min(w, h) >= 360 and get_duration(path) >= 11.0
    except Exception:
        return False

def download_gameplay(game_name, channel_url):
    output_path = os.path.join(WORK, "source.mp4")
    if os.path.exists(output_path):
        os.remove(output_path)

    log(f"Downloading raw gameplay for {game_name}...")
    cmd = [
        "yt-dlp",
        "--playlist-end", "1", 
        "--match-filter", "duration > 60 & !is_live",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "-o", output_path,
        channel_url
    ]
    
    try:
        subprocess.run(cmd, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if valid_gameplay_video(output_path):
            return output_path
    except Exception as e:
        log(f"Download failed: {e}")
    return None

def slice_video(src, start_time, duration, out_path):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(start_time), "-i", src, "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        out_path
    ]
    subprocess.run(cmd, check=True)
    return out_path

def generate_script(game):
    log(f"Generating script for {game['name']}...")
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = f"Write a 3-clip YouTube Shorts script for {game['name']}. Return strict JSON: {{\"title\": \"...\", \"hook\": \"...\", \"clips\": [\"...\", \"...\", \"...\"]}}. Keep it fast paced."
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        data = json.loads(res.text[res.text.find("{"):res.text.rfind("}")+1])
        return data
    except Exception as e:
        log(f"LLM failed: {e}")
        return game["fallback_script"]

async def tts_async(text, out):
    comm = edge_tts.Communicate(text, VOICE, rate="+8%", pitch="-2Hz")
    await comm.save(out)

def synthesize(text, out_path):
    try:
        asyncio.run(tts_async(text, out_path))
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
        # Simple 3-line sequential rendering
        for i, line in enumerate(lines):
            start = i * 12
            end = start + 12
            f.write(f"Dialogue: 0,0:00:{start:02d}.00,0:00:{end:02d}.00,Default,,0,0,0,,{line}\n")

def upload(path, title, tags):
    if DRY_RUN: return
    creds = Credentials(
        token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    yt = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title[:100], "description": "Subscribe!", "tags": tags, "categoryId": "20"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=1024*1024*5, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    req.execute()
    log("Uploaded successfully!")

def main():
    os.makedirs(WORK, exist_ok=True)
    algo = analyze_channel_algorithm()
    game = GAMES[0] # Fallback to Minecraft for testing
    
    src = download_gameplay(game["name"], game["channel"])
    if not src:
        log("No source video found. Aborting.")
        return

    script = generate_script(game)
    
    # 1. Audio
    full_text = script["hook"] + " " + " ".join(script["clips"])
    audio_path = synthesize(full_text, os.path.join(WORK, "voice.mp3"))
    
    # 2. Video Slicing (3 clips)
    segments = []
    for i in range(3):
        seg_path = os.path.join(WORK, f"seg_{i}.mp4")
        start = random.randint(10, 40) # Grab a random slice from the gameplay
        slice_video(src, start, 12, seg_path)
        segments.append(seg_path)
        
    concat_txt = os.path.join(WORK, "concat.txt")
    with open(concat_txt, "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
        
    joined = os.path.join(WORK, "joined.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", joined], check=True)
    
    # 3. Subtitles
    ass_path = os.path.join(WORK, "subs.ass")
    build_ass([script["hook"]] + script["clips"], ass_path)
    
    # 4. Final Render
    final_path = os.path.join(WORK, "final.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", joined, "-i", audio_path,
        "-vf", "ass=subs.ass",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", final_path
    ], check=True, cwd=WORK)
    
    # 5. Upload
    upload(final_path, script["title"], game["tags"])

if __name__ == "__main__":
    main()
