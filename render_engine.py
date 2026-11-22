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
    clean = re.sub(r"[#*\x60_~\\[\\]()]","", script_text).strip()
    voice = random.choice(NEURAL_VOICES)
    try:
        asyncio.run(_tts_async(clean, out_mp3, voice))
    except Exception as primary_error:
        print(f"TTS voice {voice} failed; using Christopher fallback: {primary_error}")
        voice = "en-US-ChristopherNeural"
        asyncio.run(_tts_async(clean, out_mp3, voice))
    dur_text = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_mp3
    ], text=True, timeout=60).strip()
    dur = float(dur_text)
    if not (0.5 < dur < 180):
        raise RuntimeError(f"Generated voice duration is invalid: {dur_text!r}")
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
    """Render one validated source as a 9:16 Short with a complete voice track."""
    if not os.path.isfile(src_video) or os.path.getsize(src_video) < 100_000:
        raise RuntimeError(f"Source video is missing or too small: {src_video}")

    mp3_path, audio_dur, voice_used = synthesize_human_voice(script_text)
    target_dur = round(audio_dur + 0.35, 2)
    ass_path = build_clean_ass_captions(script_text, audio_dur)

    duration_text = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", src_video
    ], text=True, timeout=60).strip()
    source_dur = float(duration_text)
    if not (1.0 < source_dur < 86400):
        raise RuntimeError(f"Source video duration is invalid: {duration_text!r}")

    # Loop short sources rather than creating a black tail; choose a valid seek point for long sources.
    max_start = max(0.0, source_dur - target_dur - 0.25)
    clip_start = round(random.uniform(0.0, max_start), 2) if max_start > 0 else 0.0

    # Keep the full landscape frame visible. The foreground is fitted into a 16:9 canvas;
    # the blurred duplicate fills the vertical background without cropping the foreground.
    filter_graph = (
        f"[0:v]trim=start={clip_start}:duration={target_dur},setpts=PTS-STARTPTS,fps=30,split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=35,eq=brightness=-0.08[bg_blur];"
        "[fg]scale=1080:608:force_original_aspect_ratio=decrease,"
        "pad=1080:608:(ow-iw)/2:(oh-ih)/2:black[fg_fit];"
        f"[bg_blur][fg_fit]overlay=(W-w)/2:(H-h)/2,ass={ass_path}[outv]"
    )

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-stream_loop", "-1", "-i", src_video,
        "-i", mp3_path,
        "-filter_complex", filter_graph,
        "-map", "[outv]", "-map", "1:a:0",
        "-t", str(target_dur),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        out_video
    ]
    subprocess.run(command, check=True, timeout=540)
    if not os.path.isfile(out_video) or os.path.getsize(out_video) < 100_000:
        raise RuntimeError("FFmpeg completed without producing a valid output video.")

    output_duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_video
    ], text=True, timeout=60).strip())
    if abs(output_duration - target_dur) > 1.0:
        raise RuntimeError(
            f"Rendered duration mismatch: expected {target_dur:.2f}s, got {output_duration:.2f}s"
        )

    print(f"Rendered {output_duration:.2f}s Short with {voice_used}; full landscape foreground + blur background.")
    return out_video
