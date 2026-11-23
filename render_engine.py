import os, re, random, subprocess, asyncio
import edge_tts

NEURAL_VOICES = ["en-US-AndrewMultilingualNeural"]

# ASS BGR colors for animated captions; adjacent chunks never repeat a color.
PALETTE_BGR = [
    "&H0014D8FF&",  # Gold / yellow
    "&H00FFF200&",  # Electric cyan
    "&H005EFF00&",  # Neon lime
    "&H00008CFF&",  # Bright orange
    "&H00FF4DFF&",  # Hot magenta
    "&H00FFFFFF&",  # White
]


async def _tts_async(text, out_mp3, voice):
    comm = edge_tts.Communicate(text, voice, rate="-4%", pitch="-1Hz")
    audio_parts, word_boundaries = [], []
    async for chunk in comm.stream():
        if chunk.get("type") == "audio":
            audio_parts.append(chunk.get("data", b""))
        elif chunk.get("type") == "WordBoundary":
            word_boundaries.append({
                "text": chunk.get("text", ""),
                "start": float(chunk.get("offset", 0)) / 10_000_000,
                "duration": float(chunk.get("duration", 0)) / 10_000_000,
            })
    if not audio_parts:
        raise RuntimeError("Edge TTS returned no audio data")
    with open(out_mp3, "wb") as f:
        for part in audio_parts:
            f.write(part)
    return word_boundaries


def synthesize_human_voice(script_text, out_mp3="/tmp/voice.mp3"):
    clean = re.sub(r"[#*_~\[\]()]", "", script_text).strip()
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
    if not (0.5 < dur < 180):
        raise RuntimeError(f"Generated voice duration is invalid: {dur}")
    return out_mp3, dur, voice, boundaries


def build_clean_ass_captions(script_text, audio_dur, out_ass="/tmp/captions.ass", word_boundaries=None):
    words = re.findall(r"\S+", re.sub(r"[#*_~\[\]()]", "", script_text).strip())
    if not words:
        raise ValueError("Cannot create captions for an empty narration script")
    chunks = [words[i:i + 4] for i in range(0, len(words), 4)]

    valid_boundaries = bool(word_boundaries) and len(word_boundaries) >= len(words)
    if valid_boundaries:
        starts = [max(0.0, float(x["start"])) for x in word_boundaries[:len(words)]]
        ends = [
            starts[i] + max(0.01, float(word_boundaries[i].get("duration", 0)))
            for i in range(len(words))
        ]
    else:
        lengths = [max(1, len(re.sub(r"\W", "", word))) for word in words]
        total, cursor, starts, ends = sum(lengths), 0, [], []
        for length in lengths:
            starts.append(audio_dur * cursor / total)
            cursor += length
            ends.append(audio_dur * cursor / total)

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PopCap,DejaVu Sans,74,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,5,3,8,70,70,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def fmt_ts(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = max(0, sec % 60)
        return f"{h}:{m:02d}:{s:05.2f}"

    events, last_color = [], None
    for idx, chunk in enumerate(chunks):
        first = idx * 4
        last = min(len(words) - 1, first + len(chunk) - 1)
        start, end = starts[first], ends[last]
        if idx + 1 < len(chunks):
            end = max(start + 0.12, min(end, starts[(idx + 1) * 4] - 0.015))
        else:
            end = max(end, min(audio_dur + 0.2, end + 0.2))
        if end <= start:
            end = start + 0.12

        choices = [color for color in PALETTE_BGR if color != last_color]
        color = random.choice(choices or PALETTE_BGR)
        last_color = color

        top = chunk[0].upper()
        lower = " ".join(word.upper() for word in chunk[1:])
        # First word is the dominant 102% display line; remaining words stack below at 74%.
        caption = (
            "{\\an8\\c" + color +
            "\\fscx85\\fscy85\\t(0,80,\\fscx100\\fscy100)" +
            "\\bord5\\shad3\\fs102}" + top +
            "\\N{\\fs74}" + lower
        )
        events.append(
            f"Dialogue: 0,{fmt_ts(start)},{fmt_ts(end)},PopCap,,0,0,0,,{caption}"
        )

    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_ass


def render_full_bleed_short(src_video, script_text, out_video="/tmp/final_short.mp4", top_hook=""):
    """Render a 14.4-second vertical Short from two 7.2-second gameplay cuts."""
    if not os.path.isfile(src_video) or os.path.getsize(src_video) < 100_000:
        raise RuntimeError(f"Source video is missing or too small: {src_video}")

    tts_result = synthesize_human_voice(script_text)
    mp3_path, audio_dur, voice_used = tts_result[:3]
    word_boundaries = tts_result[3] if len(tts_result) > 3 else None

    target_dur = 14.4
    target_audio_dur = 14.05
    tempo = audio_dur / target_audio_dur
    if not (0.75 <= tempo <= 1.25):
        raise RuntimeError(
            f"Narration duration {audio_dur:.2f}s is too far from the 14.05s audio target; "
            "regenerate a 38–42 word script rather than heavily time-stretching the voice."
        )

    fitted_voice = "/tmp/voice_fitted.mp3"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", mp3_path, "-filter:a", f"atempo={tempo:.6f}",
        "-t", str(target_audio_dur), "-c:a", "libmp3lame", "-q:a", "3",
        fitted_voice
    ], check=True, timeout=120)

    fitted_boundaries = None
    if word_boundaries:
        fitted_boundaries = [
            {
                "text": item.get("text", ""),
                "start": float(item.get("start", 0)) / tempo,
                "duration": float(item.get("duration", 0)) / tempo,
            }
            for item in word_boundaries
        ]

    ass_path = build_clean_ass_captions(
        script_text, target_audio_dur, word_boundaries=fitted_boundaries
    )

    duration_text = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", src_video
    ], text=True, timeout=60).strip()
    source_dur = float(duration_text)
    if not (1.0 < source_dur < 86400):
        raise RuntimeError(f"Source video duration is invalid: {duration_text!r}")

    # Keep both cuts inside the middle 88% of the source, avoiding intro/outro regions.
    safe_start = source_dur * 0.06
    safe_end = source_dur * 0.94
    max_start = safe_end - 7.2
    if max_start < safe_start:
        raise RuntimeError("Source video is too short for two 7.2-second cuts after intro/outro trimming.")

    first_start = random.uniform(safe_start, max_start)
    second_ranges = []
    if first_start - 7.2 >= safe_start:
        second_ranges.append((safe_start, first_start - 7.2))
    if first_start + 7.2 <= max_start:
        second_ranges.append((first_start + 7.2, max_start))
    if second_ranges:
        chosen_range = random.choice(second_ranges)
        second_start = random.uniform(*chosen_range) if chosen_range[1] > chosen_range[0] else chosen_range[0]
    else:
        second_start = max_start if first_start <= safe_start + 0.01 else safe_start

    hook_path = "/tmp/hook_banner.txt"
    with open(hook_path, "w", encoding="utf-8") as hook_file:
        hook_file.write(re.sub(r"\s+", " ", str(top_hook or "")).strip()[:100])

    filter_graph = (
        f"[0:v]trim=start={first_start:.3f}:duration=7.2,setpts=PTS-STARTPTS,fps=30,setsar=1[cut1];"
        f"[0:v]trim=start={second_start:.3f}:duration=7.2,setpts=PTS-STARTPTS,fps=30,setsar=1[cut2];"
        "[cut1][cut2]concat=n=2:v=1:a=0[game];"
        "[game]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,"
        "unsharp=5:5:0.8:5:5:0.0,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"textfile={hook_path}:fontcolor=white:fontsize=46:box=1:"
        f"boxcolor=black@0.82:boxborderw=18:x=(w-text_w)/2:y=105,"
        f"ass={ass_path}[outv]"
    )

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", src_video, "-i", fitted_voice,
        "-filter_complex", filter_graph,
        "-map", "[outv]", "-map", "1:a:0",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-t", str(target_dur),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        out_video,
    ]
    subprocess.run(command, check=True, timeout=540)
    if not os.path.isfile(out_video) or os.path.getsize(out_video) < 100_000:
        raise RuntimeError("FFmpeg completed without producing a valid output video.")

    output_duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_video
    ], text=True, timeout=60).strip())
    if abs(output_duration - target_dur) > 0.25:
        raise RuntimeError(
            f"Rendered duration mismatch: expected {target_dur:.2f}s, got {output_duration:.2f}s"
        )

    print(
        f"Rendered {output_duration:.2f}s Short with {voice_used}; "
        "two 7.2s gameplay cuts, full-bleed 9:16 crop, 6% intro/outro exclusion, hook banner and synced captions."
    )
    return out_video
