import os
import re
import json
import random
import asyncio
import datetime
import subprocess
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
import edge_tts

WORK = "/tmp/build"
VOICE = "en-US-AndrewMultilingualNeural"
DRY_RUN = os.environ.get("DRY_RUN") == "1"

GAMES = [
    {
        "name": "GTA 6",
        "channel": "https://www.youtube.com/@RockstarGames/videos",
        "tags": ["GTA 6", "GTA VI", "Vice City", "GTA 6 Trailer", "GTA 6 Gameplay", "Rockstar Games", "GTA 6 Leaks", "GTA 6 News", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "The GTA 6 Detail That Changes EVERYTHING! #shorts",
            "description": "Subscribe for daily GTA 6 news and breakdowns! This hidden detail in Vice City will blow your mind. #gta6 #vicecity #gaming #shorts",
            "hook": "This one GTA 6 mechanic completely breaks everything we knew about Rockstar games.",
            "clips": [
                "Look at the water physics in the trailer. Every ripple reacts perfectly to the boat wake.",
                "Now look at the NPC density on the beach. It is triple what GTA 5 could handle.",
                "And the traffic lights downtown actually sync up realistically. This game is insane."
            ]
        }
    },
    {
        "name": "GTA 5",
        "channel": "https://www.youtube.com/@NoCopyrightGameplays/videos",
        "tags": ["GTA 5", "GTA 5 Myths", "GTA 5 Gameplay", "GTA 5 Stunts", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "3 GTA 5 Stunts That BROKE Physics! #shorts",
            "description": "Insane GTA 5 physics moments. Subscribe for more gaming shorts! #gta5 #gaming #shorts",
            "hook": "Watch these three crazy GTA 5 moments that literally broke the game engine.",
            "clips": [
                "First, look at how the ragdoll physics react when launching off Mount Chiliad.",
                "Second, watch what happens when NPC traffic glitches during a five-star chase.",
                "And third, this pilot threads a jet through the tightest tunnel on the map."
            ]
        }
    }
]

GAME_WEIGHTS = [0.9, 0.1] 

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

def download_youtube_fallback(game):
    output_path = os.path.join(WORK, "source.mp4")
    log(f"Downloading gameplay for {game['name']} with PO Token...")
    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=web;getpot_bgutil_baseurl=http://127.0.0.1:4416",
        "--playlist-end", "3",
        "--match-filter", "duration > 30 & !is_live",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "-o", output_path,
        game["channel"]
    ]
    try:
        subprocess.run(cmd, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if valid_video(output_path): return output_path
    except: pass
    return None

def safe_auto_edit_and_slice(src):
    log("Running Auto-Editor to cut dead space...")
    edited_path = os.path.join(WORK, "edited_source.mp4")
    cmd_edit = [
        "auto-editor", src, 
        "--edit", "audio:threshold=0.04",
        "--margin", "0.2sec",
        "-o", edited_path
    ]
    try:
        subprocess.run(cmd_edit, check=True, timeout=300)
    except Exception as e:
        log(f"Auto-editor failed, using original: {e}")
        edited_path = src

    log("Slicing 3 segments from the clean edit...")
    segments = []
    for i in range(3):
        seg_path = os.path.join(WORK, f"seg_{i}.mp4")
        start = random.randint(0, max(1, int(get_duration(edited_path)) - 15))
        cmd_slice = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", edited_path, "-t", "12", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", seg_path]
        subprocess.run(cmd_slice, check=True)
        segments.append(seg_path)
    return segments

def generate_script(game):
    log(f"Generating ANALYTICAL Script for {game['name']}...")
    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = f"""
        You are a professional gaming analyst. Write a YouTube Shorts script for {game['name']}. 
        CRITICAL RULE: You must add significant commentary, analysis, or a unique theory. 
        Do NOT just describe what happens on screen. Explain WHY it matters or what it means for the game.
        
        Return strict JSON format only: 
        {{
            "title": "<Under 90 chars, massive clickbait, MUST end with #shorts>",
            "description": "<2 sentences of analysis. Include 'Subscribe for more!' and 5 hashtags>",
            "hook": "<One controversial or mind-blowing analytical sentence>",
            "clips": ["<clip 1: analysis>", "<clip 2: analysis>", "<clip 3: analysis>"]
        }}
        """
        res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        data = json.loads(res.text[res.text.find("{"):res.text.rfind("}")+1])
        if "description" not in data or not data["description"]:
            data["description"] = game["fallback_script"]["description"]
        return data
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

def upload(path, title, description, tags):
    if DRY_RUN: return
    creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "20"}, 
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=1024*1024*5, resumable=True)
    yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    log(f"Uploaded: {title}")

def main():
    os.makedirs(WORK, exist_ok=True)
    game = random.choices(GAMES, weights=GAME_WEIGHTS, k=1)[0]
    log(f"Selected Game for this run: {game['name']}")
    
    src = download_youtube_fallback(game)
    if not src:
        log("No source video found. Aborting.")
        return

    script = generate_script(game)
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
    
    upload(final_path, script["title"], script["description"], game["tags"])

if __name__ == "__main__":
    main()
