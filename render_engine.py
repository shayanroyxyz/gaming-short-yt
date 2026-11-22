import os, re, json, math, random, subprocess, asyncio
import edge_tts

NEURAL_VOICES = [
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural"
]

# ASS BGR color codes (&HBBGGRR&) for vibrant randomized pop captions (like "STEAL MY CAPTION STYLE")
PALETTE_BGR = [
    "&H0014D8FF&",  # Vibrant Gold/Yellow
    "&H00FFF200&",  # Electric Cyan
    "&H005EFF00&",  # Neon Lime Green
    "&H00008CFF&",  # Bright Orange
    "&H00FF4DFF&",  # Hot Magenta
    "&H00FFFFFF&"   # Crisp Pure White
]

async def _tts_async(text, out_mp3, voice):
    comm = edge_tts.Communicate(text, voice, rate="+6%", pitch="-1Hz")
    await comm.save(out_mp3)

def synthesize_human_voice(script_text, out_mp3="/tmp/voice.mp3"):
    clean = re.sub(r"[#*`_~\[\]()]", "", script_text).strip()
    voice = random.choice(NEURAL_VOICES)
    try:
        asyncio.run(_tts_async(clean, out_mp3, voice))
    except Exception:
        # Fallback voice if primary fails
        asyncio.run(_tts_async(clean, out_mp3, "en-US-ChristopherNeural"))
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_mp3
    ], text=True).strip())
    return out_mp3, dur, voice

def build_clean_ass_captions(script_text, audio_dur, out_ass="/tmp/captions.ass"):
    words = [w.strip() for w in re.sub(r"[^a-zA-Z0-9\s\x27!?.-]", "", script_text).split() if w.strip()]
    if not words:
        words = ["WATCH", "THIS", "SECRET"]

    # Group into punchy 2-3 word chunks so text never overflows or overlaps
    chunks = []
    i = 0
    while i < len(words):
        step = 2 if (i % 4 == 0 or len(words[i]) > 7) else 3
        chunks.append(" ".join(words[i:i+step]).upper())
        i += step

    total_chars = sum(len(c) for c in chunks) or 1
    t_cursor = 0.05

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PopCap,Arial Black,84,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,1,0,1,6,4,8,70,70,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt_ts(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    events = []
    last_color = ""
    for idx, chunk in enumerate(chunks):
        share = (len(chunk) / total_chars) * max(audio_dur - 0.1, 1.0)
        start_t = t_cursor
        end_t = min(audio_dur + 0.15, start_t + max(share, 0.35))
        if idx == len(chunks) - 1:
            end_t = audio_dur + 0.2
        t_cursor = end_t

        # Pick randomized color (never same twice in a row)
        choices = [c for c in PALETTE_BGR if c != last_color]
        color = random.choice(choices)
        last_color = color

        # Split into 2 stacked lines if 3 words so it matches "STEAL / MY CAPTION / STYLE"
        parts = chunk.split()
        if len(parts) == 3:
            display = f"{parts[0]}\\N{parts[1]} {parts[2]}"
        elif len(parts) == 2 and len(chunk) > 11:
            display = f"{parts[0]}\\N{parts[1]}"
        else:
            display = chunk

        events.append(
            f"Dialogue: 0,{fmt_ts(start_t)},{fmt_ts(end_t)},PopCap,,0,0,0,,{{\\c{color}}}{display}"
        )

    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_ass

def render_blur_landscape_short(src_video, script_text, out_video="/tmp/final_short.mp4"):
    mp3_path, audio_dur, voice_used = synthesize_human_voice(script_text)
    target_dur = round(audio_dur + 0.35, 2)
    ass_path = build_clean_ass_captions(script_text, audio_dur)

    vid_dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", src_video
    ], text=True).strip())

    # Pick 2 clean non-intro action slices that together match the FULL voiceover duration
    half = target_dur / 2.0
    safe_start = min(15.0, vid_dur * 0.1)
    safe_end = max(safe_start + half + 1.0, vid_dur - half - 5.0)
    t1 = round(random.uniform(safe_start, max(safe_start + 0.5, safe_end - half)), 2)
    t2 = round(random.uniform(safe_start, max(safe_start + 0.5, safe_end)), 2)

    # Full 16:9 landscape centered (1080x608) over smooth blurred 9:16 background + clean ASS captions
    fc = (
        f"[0:v]trim=start={t1}:duration={half + 0.2},setpts=PTS-STARTPTS[v1];"
        f"[0:v]trim=start={t2}:duration={half + 0.2},setpts=PTS-STARTPTS[v2];"
        f"[v1][v2]concat=n=2:v=1:a=0,fps=30,split=2[bg][fg];"
        f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=35,eq=brightness=-0.08[bg_blur];"
        f"[fg]scale=1080:-2[fg_fit];"
        f"[bg_blur][fg_fit]overlay=(W-w)/2:(H-h)/2,ass={ass_path}[outv]"
    )

    subprocess.run([
        "ffmpeg", "-y", "-i", src_video, "-i", mp3_path,
        "-filter_complex", fc,
        "-map", "[outv]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(target_dur),
        out_video
    ], check=True)
    print(f"✅ Rendered {target_dur}s blur-bg Short with voice {voice_used}")
    return out_video
