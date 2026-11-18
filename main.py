import os
import re
import json
import random
import time
import asyncio
import datetime
import subprocess
import requests
import xml.etree.ElementTree as ET
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google import genai
import edge_tts

WORK = "/tmp/build"
VOICE = "en-US-AndrewMultilingualNeural"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
IG_COOKIE_FILE = "/tmp/ig_cookies.txt"

X_CREATORS = ["GTA6Intel", "RockstarGames", "GTAVclips", "Minecraft", "Roblox"]
IG_REELS = ["https://www.instagram.com/reel/DXW4z-7jiAi/"]

GAMES = [
    {
        "name": "GTA V",
        "search_query": "GTA 5 gameplay",
        "tags": ["GTA 5", "GTAV", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "GTA 5 Secrets You Never Noticed! #shorts",
            "description": "Subscribe for daily GTA content! #gta5 #gaming #shorts",
            "hook": "These three GTA 5 details completely change how you play.",
            "clips": ["First, look at the water physics.", "Second, the NPC density.", "And third, the traffic lights."]
        }
    },
    {
        "name": "GTA 6 Trailer",
        "search_query": "GTA 6 trailer",
        "tags": ["GTA 6", "GTA VI", "Vice City", "Gaming", "Shorts"],
        "fallback_script": {
            "title": "The GTA 6 Detail That Changes EVERYTHING! #shorts",
            "description": "Subscribe for daily GTA 6 news! #gta6 #vicecity #gaming #shorts",
            "hook": "This one GTA 6 mechanic completely breaks everything.",
            "clips": ["Look at the water physics.", "Now look at the NPC density.", "And the traffic lights downtown."]
        }
    }
]

GAME_WEIGHTS = [0.6, 0.4]

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def setup_ig_cookies():
    cookies = os.environ.get("IG_COOKIES", "").strip()
    if cookies:
        with open(IG_COOKIE_FILE, "w") as f:
            f.write(cookies)
        return True
    return False

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

def download_instagram():
    if not os.path.exists(IG_COOKIE_FILE): return None
    log("Tier 1: Scanning Instagram...")
    for url in IG_REELS:
        try:
            output_path = os.path.join(WORK, "source.mp4")
            cmd = ["yt-dlp", "--cookies", IG_COOKIE_FILE, "-f", "bv*[height<=480]+ba/b[height<=480]", "-o", output_path, url]
            subprocess.run(cmd, check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if valid_video(output_path): return output_path
        except: pass
    return None

def download_twitter():
    log("Tier 2: Scanning X/Twitter...")
    for user in X_CREATORS:
        try:
            rss_url = f"https://fxtwitter.com/{user}/feed.xml"
            r = requests.get(rss_url, timeout=10)
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            if not items: continue
            link = items[0].find("link").text
            output_path = os.path.join(WORK, "source.mp4")
            cmd = ["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]", "-o", output_path, link]
            subprocess.run(cmd, check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if valid_video(output_path): return output_path
        except: pass
    return None

def download_dailymotion(game):
    log("Tier 3: Scanning Dailymotion...")
    try:
        q = requests.utils.quote(game["search_query"])
        api = f"https://api.dailymotion.com/videos?search={q}&fields=id,url&limit=5"
        r = requests.get(api, timeout=10).json()
        for v in r.get("list", []):
            url = f"https://www.dailymotion.com/video/{v['id']}"
            output_path = os.path.join(WORK, "source.mp4")
            cmd = ["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]", "-o", output_path, url]
            subprocess.run(cmd, check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if valid_video(output_path): return output_path
    except: pass
    return None

def download_archive(game):
    log("Tier 4: Scanning Internet Archive...")
    try:
        api_url = f"https://archive.org/advancedsearch.php?q={requests.utils.quote(game['search_query'])}&fl[]=identifier&rows=10&output=json"
        r = requests.get(api_url, timeout=20).json()
        docs = r.get("response", {}).get("docs", [])
        random.shuffle(docs)
        for doc in docs:
            ident = doc.get("identifier")
            if not ident: continue
            meta = requests.get(f"https://archive.org/metadata/{ident}", timeout=15).json()
            for f in meta.get("files", []):
                name = f.get("name", "")
                size = int(f.get("size", 0) or 0)
                if name.lower().endswith(".mp4") and 1_000_000 < size < 50_000_000:
                    output_path = os.path.join(WORK, "source.mp4")
                    dl_url = f"https://archive.org/download/{ident}/{name}"
                    res = subprocess.run(["curl", "-L", "-f", "-o", output_path, dl_url], timeout=120)
                    if res.returncode == 0 and valid_video(output_path): return output_path
    except: pass
    return None

def get_source_video(game):
    output_path = os.path.join(WORK, "source.mp4")
    if os.path.exists(output_path): os.remove(output_path)
    
    for func in [download_instagram, download_twitter]:
        src = func()
        if src: return src
        
    for func in [download_dailymotion, download_archive]:
        src = func(game)
        if src: return src
    return None

def safe_auto_edit_and_slice(src):
    log("Running Auto-Editor...")
    edited_path = os.path.join(WORK, "edited_source.mp4")
    try: 
        subprocess.run(["auto-editor", src, "--edit", "audio:threshold=0.04", "--margin", "0.2sec", "-o", edited_path], check=True, timeout=120)
    except: 
        edited_path = src

    log("Slicing & Applying Effects...")
    segments = []
    for i in range(3):
        seg_path = os.path.join(WORK, f"seg_{i}.mp4")
        start = random.randint(0, max(1, int(get_duration(edited_path)) - 15))
        
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0015,1.5)':d=1:s=1080x1920"
        if random.choice([True, False]): vf += ",hflip"
        af = "loudnorm=I=-14:TP=-1.5:LRA=11,highpass=f=80,lowpass=f=12000"

        cmd_slice = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", edited_path, "-t", "12", "-vf", vf, "-af", af, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", seg_path]
        subprocess.run(cmd_slice, check=True)
        segments.append(seg_path)
    return segments

# --- AI BRAIN (FIXED TO PREVENT DUPLICATES) ---
def call_gemini(prompt):
    try:
        key = os.environ.get("GEMINI_API_KEY")
        if not key: return None
        client = genai.Client(api_key=key)
        # Temperature 1.0 forces the AI to be highly creative and unique
        return client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt,
            config={'temperature': 1.0} 
        ).text
    except: return None

def call_pollinations(prompt):
    try:
        r = requests.post("https://text.pollinations.ai/openai", json={"model": "openai", "messages": [{"role": "user", "content": prompt}], "temperature": 1.0}, timeout=30)
        return r.json()['choices'][0]['message']['content']
    except: return None

def generate_script(game_name, rules=""):
    log(f"Generating Script for {game_name}...")
    
    # WE ADD A RANDOM NUMBER SO THE AI NEVER GENERATES THE SAME TITLE TWICE
    random_seed = random.randint(1000, 9999)
    
    prompt = f"""
    You are a viral YouTube Shorts strategist. Write a script for {game_name}. 
    RULES: {rules}
    RANDOM SEED (Use this to make the title unique): {random_seed}
    
    Return ONLY valid JSON: 
    {{
        "title": "<Max 80 chars, unique clickbait, MUST end with #shorts>", 
        "description": "<2 sentences>", 
        "hook": "<Curiosity gap>", 
        "clips": ["<clip 1>", "<clip 2>", "<clip 3>"]
    }}
    """
    
    res = call_gemini(prompt)
    if not res: res = call_pollinations(prompt)
    if not res: return GAMES[0]["fallback_script"]

    try:
        return json.loads(res[res.find("{"):res.rfind("}")+1])
    except: return GAMES[0]["fallback_script"]

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
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags, "categoryId": "20"}, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=1024*1024*5, resumable=True)
    response = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    log(f"✅ SUCCESS! Video ID: {response['id']}")

def main():
    os.makedirs(WORK, exist_ok=True)
    setup_ig_cookies()
    
    # 5 SECOND DELAY TO PREVENT GITHUB API OVERLAPS
    time.sleep(5)
    
    manual_url = os.environ.get("CAMPAIGN_URL", "").strip()
    manual_game = os.environ.get("GAME_OVERRIDE", "").strip()
    manual_rules = os.environ.get("GUIDELINES", "").strip()
    
    if manual_url:
        log("MANUAL CAMPAIGN MODE")
        src = os.path.join(WORK, "source.mp4")
        subprocess.run(["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]", "-o", src, manual_url], check=True)
        game, rules = manual_game or "Gaming", manual_rules
    else:
        selected_game = random.choices(GAMES, weights=GAME_WEIGHTS, k=1)[0]
        log(f"AUTO MODE: {selected_game['name']}")
        src = get_source_video(selected_game)
        game, rules = selected_game["name"], ""

    if not src:
        log("All sources failed. Aborting.")
        return

    script = generate_script(game, rules)
    segments = safe_auto_edit_and_slice(src)
    
    audio_path = synthesize(script["hook"] + " " + " ".join(script["clips"]), os.path.join(WORK, "voice.mp3"))
    
    with open(os.path.join(WORK, "concat.txt"), "w") as f:
        for s in segments: f.write(f"file '{s}'\n")
        
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(WORK, "concat.txt"), "-c", "copy", os.path.join(WORK, "joined.mp4")], check=True)
    
    build_ass([script["hook"]] + script["clips"], os.path.join(WORK, "subs.ass"))
    
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(WORK, "joined.mp4"), "-i", audio_path, "-vf", "ass=subs.ass", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", "-shortest", os.path.join(WORK, "final.mp4")], check=True, cwd=WORK)
    
    upload(os.path.join(WORK, "final.mp4"), script["title"], script["description"], ["gaming", "shorts", game])

if __name__ == "__main__":
    main()
