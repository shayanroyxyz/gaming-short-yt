import os, re, json, math, random, subprocess, asyncio
import edge_tts

NEURAL_VOICES = ["en-US-AndrewMultilingualNeural"]

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
    audio_parts, word_boundaries = [], []
    async for chunk in comm.stream():
        if chunk.get("type") == "audio":
            audio_parts.append(chunk.get("data", b""))
        elif chunk.get("type") == "WordBoundary":
            word_boundaries.append({"text": chunk.get("text", ""),
                "start": float(chunk.get("offset", 0)) / 10000000,
                "duration": float(chunk.get("duration", 0)) / 10000000})
    if not audio_parts:
        raise RuntimeError("Edge TTS returned no audio data")
    with open(out_mp3, "wb") as f:
        for part in audio_parts: f.write(part)
    return word_boundaries

def synthesize_human_voice(script_text, out_mp3="/tmp/voice.mp3"):
    clean = re.sub(r"[#*_~\[\]()], "", script_text).strip()
    voice = "en-US-AndrewMultilingualNeural"
    try:
        boundaries = asyncio.run(_tts_async(clean, out_mp3, voice))
    except Exception as exc:
        print(f"TTS voice {voice} failed; using Christopher fallback: {exc}")
        voice = "en-US-ChristopherNeural"
        boundaries = asyncio.run(_tts_async(clean, out_mp3, voice))
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_mp3
    ], text=True, timeout=60).strip())
    if not (0.5 < dur < 180): raise RuntimeError(f"Generated voice duration is invalid: {dur}")
    return out_mp3, dur, voice, boundaries

def build_clean_ass_captions(script_text, audio_dur, out_ass="/tmp/captions.ass", word_boundaries=None):
    words = re.findall(r"\S+", re.sub(r"[#*_~\\[\\]()]", "", script_text).strip())
    if not words: raise ValueError("Cannot create captions for an empty narration script")
    chunks = [words[i:i+4] for i in range(0, len(words), 4)]
    valid_boundaries = bool(word_boundaries) and len(word_boundaries) >= len(words)
    if valid_boundaries:
        starts = [max(0.0, float(x["start"])) for x in word_boundaries[:len(words)]]
        ends = [starts[i] + max(0.01, float(word_boundaries[i].get("duration", 0))) for i in range(len(words))]
    else:
        lengths = [max(1, len(re.sub(r"\W", "", w))) for w in words]
        total, cursor, starts, ends = sum(lengths), 0, [], []
        for n in lengths:
            starts.append(audio_dur * cursor / total); cursor += n
            ends.append(audio_dur * cursor / total)

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PopCap,DejaVu Sans,76,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,5,3,8,70,70,240,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt_ts(sec):
        h, m, s = int(sec // 3600), int((sec % 3600) // 60), max(0, sec % 60)
        return f"{h}:{m:02d}:{s:05.2f}"
    events, last_color = [], None
    for idx, chunk in enumerate(chunks):
        first, last = idx*4, min(len(words)-1, idx*4+len(chunk)-1)
        st, en = starts[first], ends[last]
        if idx+1 < len(chunks): en = max(st+0.12, min(en, starts[(idx+1)*4]-0.015))
        else: en = max(en, min(audio_dur+0.2, en+0.2))
        if en <= st: en = st+0.12
        palette = [x for x in PALETTE_BGR if x != last_color]
        color = random.choice(palette or PALETTE_BGR); last_color = color
        top, lower = chunk[0].upper(), " ".join(x.upper() for x in chunk[1:])
        text = "{\\an8\\c" + color + "\\fscx85\\fscy85\\t(0,80,\\fscx100\\fscy100)\\bord5\\shad3\\fs82}" + top + "\\N{\\fs66}" + lower
        events.append(f"Dialogue: 0,{fmt_ts(st)},{fmt_ts(en)},PopCap,,0,0,0,,{text}")
    with open(out_ass, "w", encoding="utf-8") as f: f.write(header + "\n".join(events) + "\n")
    return out_ass

def render_blur_landscape_short(src_video, script_text, out_video="/tmp/final_short.mp4"):
    """Render one validated source as a 9:16 Short with a complete voice track."""
    if not os.path.isfile(src_video) or os.path.getsize(src_video) < 100_000:
        raise RuntimeError(f"Source video is missing or too small: {src_video}")

    tts_result = synthesize_human_voice(script_text)
    mp3_path, audio_dur, voice_used = tts_result[:3]
    word_boundaries = tts_result[3] if len(tts_result) > 3 else None
    target_dur = round(audio_dur + 0.35, 2)
    ass_path = build_clean_ass_captions(script_text, audio_dur, word_boundaries=word_boundaries)

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
