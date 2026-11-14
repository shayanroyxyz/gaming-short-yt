import os
import random
import subprocess
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.generativeai as genai

def fetch_clip():
    with open("sources.txt") as f:
        feeds = [line.strip() for line in f if line.strip()]
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GTA6Bot/1.0"}
    video_urls = []

    for feed in feeds:
        try:
            r = requests.get(feed, headers=headers, timeout=15).json()
            for post in r.get("data", {}).get("children", []):
                data = post.get("data", {})
                if data.get("is_video") and data.get("media", {}).get("reddit_video", {}).get("duration", 99) <= 58:
                    video_urls.append((data.get("title", "GTA 6 Clip"), "https://www.reddit.com" + data.get("permalink")))
        except Exception as e:
            print("Feed error:", e)

    if not video_urls:
        raise RuntimeError("No valid short videos found in feeds.")

    topic, chosen_url = random.choice(video_urls)
    print("Downloading:", topic, chosen_url)
    subprocess.run([
        "yt-dlp",
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "-o", "raw.mp4",
        chosen_url
    ], check=True)
    return topic

def transform_video():
    crop_w = random.choice([880, 900, 920])
    crop_h = random.choice([1560, 1600, 1630])
    speed = random.choice(["0.97", "1.03"])
    subprocess.run([
        "ffmpeg", "-y", "-i", "raw.mp4",
        "-vf", f"setpts={speed}*PTS,scale=1080:1920:force_original_aspect_ratio=increase,crop={crop_w}:{crop_h},scale=1080:1920,eq=contrast=1.12:saturation=1.18",
        "-af", "asetrate=44100*1.02,aresample=44100",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "final.mp4"
    ], check=True)

def generate_metadata(topic):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    res = model.generate_content(
        f"Topic: {topic}\nWrite 1 viral YouTube Short title under 85 chars with #shorts #gta6 on line 1, and a 2-line description on lines 2-3."
    )
    lines = [l.strip() for l in res.text.strip().split("\n") if l.strip()]
    return lines[0][:85], "\n".join(lines[1:]) or "#shorts #gta6"

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
                "tags": ["GTA6", "GTA6Clips", "Shorts"],
                "categoryId": "20"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        },
        media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    )
    resp = req.execute()
    print("Uploaded Video ID:", resp.get("id"))

if __name__ == "__main__":
    topic = fetch_clip()
    transform_video()
    title, desc = generate_metadata(topic)
    upload_video(title, desc)
