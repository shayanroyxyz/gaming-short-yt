#!/usr/bin/env python3
"""Build an original-commentary GTA Short from a permitted direct video URL."""
import asyncio, json, os, random, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse
import edge_tts, requests
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
RAW, AUDIO, SRT, OUTPUT = [ROOT / n for n in ("source_video", "voice.mp3", "captions.srt", "final.mp4")]
VOICE = "en-US-AndrewMultilingualNeural"

def require_secrets():
    names = ["GEMINI_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [n for n in names if not os.getenv(n, "").strip()]
    if missing:
        raise RuntimeError("Missing GitHub Actions secret(s): " + ", ".join(missing))

def read_sources():
    entries = []
    for number, line in enumerate((ROOT / "sources.txt").read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = [x.strip() for x in line.split("|", 2)]
        if len(fields) != 3 or not all(fields):
            raise RuntimeError(f"sources.txt line {number}: expected URL | topic | creator/licence/permission credit")
        url, topic, credit = fields
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or not re.search(r"\.(mp4|mov|m4v|webm)(?:$|[?#])", url, re.I):
            raise RuntimeError(f"sources.txt line {number}: use a direct HTTPS video URL ending in mp4, mov, m4v, or webm")
        entries.append({"url": url, "topic": topic, "credit": credit})
    if not entries:
        raise RuntimeError("No permitted clip configured. Add a direct video URL to sources.txt. Only use footage you are allowed to reuse.")
    return entries

def download_clip(entry):
    print("Downloading source for:", entry["topic"], flush=True)
    total = 0
    with requests.get(entry["url"], headers={"User-Agent": "GTA-Shorts-Commentary/1.0"}, stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        ctype = response.headers.get("Content-Type", "").lower()
        if "text/html" in ctype or "json" in ctype:
            raise RuntimeError("URL returned a webpage/API response, not a direct video file.")
        with RAW.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    total += len(chunk)
                    if total > 300 * 1024 * 1024:
                        raise RuntimeError("Source video exceeds 300 MB limit.")
                    output.write(chunk)
    if total < 10000:
        raise RuntimeError("Downloaded source is too small to be a valid video.")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(RAW)], capture_output=True, text=True)
    if probe.returncode:
        raise RuntimeError("Downloaded file is not a readable video. Use a direct media URL.")
    duration = float(probe.stdout.strip())
    if duration < 3:
        raise RuntimeError("Source video must be at least 3 seconds.")
    print(f"Source downloaded: {total / 1048576:.1f} MB, {duration:.1f}s", flush=True)

def generate_script(topic, credit):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = f"""
Write original commentary for a GTA 5 / GTA 6 YouTube Short.
Topic: {topic}
Source credit: {credit}
Return ONLY JSON with keys narration, title, description, tags.
Narration: 45-65 spoken words, conversational, no claims of personal gameplay.
Do not invent leaks, confirmed features, dates, or facts. Label speculation clearly.
Do not describe visual details you cannot verify.
Title: accurate, under 90 characters.
Description: 1-3 sentences and include this exact credit: {credit}
Tags: array of 3-8 relevant plain-text tags.
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = (response.text or "").strip()
    tick = chr(96)
    raw = raw.replace(tick * 3 + "json", "").replace(tick * 3, "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned invalid JSON; re-run the workflow.") from exc
    narration = re.sub(r"\s+", " ", str(data.get("narration", ""))).strip()
    title = re.sub(r"\s+", " ", str(data.get("title", ""))).strip()[:90]
    description = str(data.get("description", "")).strip()
    tags = data.get("tags", [])
    if not narration or not title or not description:
        raise RuntimeError("Gemini response missing narration, title, or description.")
    if len(narration.split()) > 85:
        raise RuntimeError("Generated narration too long; re-run.")
    if not isinstance(tags, list):
        tags = []
    tags = [re.sub(r"[^A-Za-z0-9 #_-]", "", str(t)).strip()[:30] for t in tags]
    tags = [t for t in tags if t][:9]
    if not any(t.lower().lstrip("#") == "shorts" for t in tags):
        tags.append("Shorts")
    if credit.lower() not in description.lower():
        description += "\n\nFootage credit/licence: " + credit
    description += "\n\nOriginal AI-assisted commentary. Footage credit/licence is identified above."
    return narration, title, description, tags[:10]

def srt_time(seconds):
    ms = max(0, int(seconds * 1000))
    h, r = divmod(ms, 3600000); m, r = divmod(r, 60000); s, ms = divmod(r, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

async def make_voice_and_captions(text):
    tts = edge_tts.Communicate(text, VOICE, rate="+8%", pitch="-2Hz")
    audio, boundaries = [], []
    async for item in tts.stream():
        if item["type"] == "audio":
            audio.append(item["data"])
        elif item["type"] == "WordBoundary":
            boundaries.append({"start": item["offset"] / 10000000, "duration": item["duration"] / 10000000, "word": item["text"].strip()})
    if not audio:
        raise RuntimeError("Edge TTS returned no audio.")
    AUDIO.write_bytes(b"".join(audio))
    words = [w for w in boundaries if w["word"]]
    rows = []
    if words:
        for i in range(0, len(words), 4):
            group = words[i:i+4]
            start = group[0]["start"]
            end = max(start + 0.35, group[-1]["start"] + group[-1]["duration"])
            rows.append((start, end, " ".join(w["word"] for w in group)))
    else:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(AUDIO)], capture_output=True, text=True, check=True)
        duration = float(p.stdout.strip())
        sentences = re.split(r"(?<=[.!?])\s+", text)
        step = duration / max(1, len(sentences))
        rows = [(i*step, min(duration, (i+1)*step), sentence) for i, sentence in enumerate(sentences)]
    lines = []
    for i, (start, end, caption) in enumerate(rows, 1):
        lines.extend([str(i), f"{srt_time(start)} --> {srt_time(end)}", caption, ""])
    SRT.write_text("\n".join(lines), encoding="utf-8")

def render_video():
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,"
          "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30,"
          "subtitles=captions.srt:force_style='FontName=DejaVu Sans,FontSize=20,"
          "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
          "Outline=3,Shadow=1,Alignment=2,MarginV=190'")
    subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", str(RAW), "-i", str(AUDIO),
        "-map", "0:v:0", "-map", "1:a:0", "-vf", vf, "-t", "58",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(OUTPUT)], check=True)
    if not OUTPUT.exists() or OUTPUT.stat().st_size < 50000:
        raise RuntimeError("FFmpeg did not create a valid final.mp4.")

def upload(title, description, tags):
    creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token", scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    request = youtube.videos().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "20", "defaultLanguage": "en"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}},
        media_body=MediaFileUpload(str(OUTPUT), mimetype="video/mp4", chunksize=8*1024*1024, resumable=True))
    result = request.execute()
    video_id = result.get("id")
    if not video_id:
        raise RuntimeError("YouTube API did not return a video ID.")
    print("UPLOAD_SUCCESS video_id=" + video_id, flush=True)
    print("https://www.youtube.com/shorts/" + video_id, flush=True)

def main():
    require_secrets()
    entry = random.choice(read_sources())
    download_clip(entry)
    narration, title, description, tags = generate_script(entry["topic"], entry["credit"])
    print("Title:", title, flush=True)
    print("Creating Andrew Multilingual voice and synced captions...", flush=True)
    asyncio.run(make_voice_and_captions(narration))
    render_video()
    upload(title, description, tags)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"AUTOMATION_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
