import os
import random
import asyncio
import textwrap
import subprocess
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.generativeai as genai

def validate_env():
    required = ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing GitHub Secrets: {', '.join(missing)}")

def fetch_and_slice_clip():
    with open("sources.txt") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if not urls:
        raise RuntimeError("sources.txt has no URLs!")
    source_url = random.choice(urls)
    print("Downloading source clip from:", source_url)
    subprocess.run(["yt-dlp", "-f", "mp4/best", "-o", "full_source.mp4", source_url], check=True)

    start_sec = random.randint(5, 65)
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-t", "18",
        "-i", "full_source.mp4", "-c", "copy", "raw.mp4"
    ], check=True)

def generate_ai_script_and_metadata():
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    topics = [
        "insane NPC crowd density and beach physics in GTA 6",
        "hidden Vice City map details spotted in GTA 6",
        "how GTA 6 vehicle interiors and reflections beat GTA 5",
        "crazy police chase and wildlife AI details in Leonida"
    ]
    chosen_topic = random.choice(topics)
    prompt = (
        f"Topic: {chosen_topic}\n"
        "Output exactly 3 lines:\n"
        "Line 1: Viral YouTube Short title under 80 chars ending with #shorts #gta6\n"
        "Line 2: Punchy, natural conversational 2-sentence commentary (25-35 words total) with natural pauses (...) for a gaming Short.\n"
        "Line 3: Bold 4-word on-screen hook caption in ALL CAPS (no emojis, no quotes)."
    )
    res = model.generate_content(prompt)
    lines = [l.strip() for l in res.text.strip().split("\n") if l.strip()]
    title = lines[0][:85]
    voice_text = lines[1] if len(lines) > 1 else "Look closely at the background details in GTA 6... Rockstar completely rebuilt the NPC AI from scratch."
    hook_caption = lines[2].replace("'", "").replace('"', '') if len(lines) > 2 else "GTA 6 HIDDEN DETAIL"
    return title, voice_text, hook_caption

async def create_humanoid_voiceover(text):
    communicate = edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural", rate="+8%", pitch="-2Hz")
    await communicate.save("voice.mp3")

def render_short(hook_caption):
    wrapped = "\n".join(textwrap.wrap(hook_caption, width=18))
    with open("caption.txt", "w") as f:
        f.write(wrapped)

    subprocess.run([
        "ffmpeg", "-y",
        "-i", "raw.mp4",
        "-i", "voice.mp3",
        "-filter_complex",
        "[0:v]setpts=0.97*PTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.12:saturation=1.18,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile=caption.txt:fontcolor=yellow:borderw=5:bordercolor=black:fontsize=70:x=(w-text_w)/2:y=230[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "final.mp4"
    ], check=True)

def upload_video(title, description):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    youtube = build("youtube", "v3", credentials=creds)
    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["GTA6", "GTA6Clips", "RockstarGames", "Shorts"],
                "categoryId": "20"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        },
        media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    )
    resp = req.execute()
    print("SUCCESS! Uploaded Video ID:", resp.get("id"))

if __name__ == "__main__":
    validate_env()
    fetch_and_slice_clip()
    title, voice_text, hook_caption = generate_ai_script_and_metadata()
    asyncio.run(create_humanoid_voiceover(voice_text))
    render_short(hook_caption)
    upload_video(title, f"{voice_text}\n\n#shorts #gta6 #gaming")
