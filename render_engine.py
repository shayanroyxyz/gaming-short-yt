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
    chunks = [words[i:i + 3] for i in range(0, len(words), 3)]

    valid_boundaries = bool(word_boundaries) and len(word_boundaries) >= len(words)
    if valid_boundaries:
        starts = [max(0.0, float(x["start"])) for x in word_boundaries[:len(words)]]
        ends = [starts[i] + max(0.01, float(word_boundaries[i].get("duration", 0))) for i in range(len(words))]
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
Style: PopCap,DejaVu Sans,72,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,5,1,5,70,70,0,1

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
        first = idx * 3
        last = min(len(words) - 1, first + len(chunk) - 1)
        start, end = starts[first], ends[last]
        if idx + 1 < len(chunks):
            end = max(start + 0.12, min(end, starts[(idx + 1) * 3] - 0.015))
        else:
            end = max(end, min(audio_dur + 0.2, end + 0.2))
        if end <= start:
            end = start + 0.12
        choices = [color for color in PALETTE_BGR if color != last_color]
        color = random.choice(choices or PALETTE_BGR)
        last_color = color
        phrase_parts = []
        for word in chunk:
            clean_word = re.sub(r"[^\w'-]", "", word).lower()
            power_word = bool(re.search(r"\d", clean_word)) or clean_word in {
                "crash", "crashes", "explodes", "exploded", "explosion", "burns",
                "burning", "chase", "chased", "police", "fastest", "impossible",
                "secret", "hidden", "survives", "survived", "breaks", "broke",
                "launch", "launches", "impact", "smashes", "destroyed", "flips",
                "flies", "flying", "falls", "escape", "escaped", "record"
            }
            color_tag = r"{\c&H0000E6FF&}" if power_word else r"{\c&H00FFFFFF&}"
            phrase_parts.append(color_tag + word.upper())
        phrase = " ".join(phrase_parts)
        caption = (
            r"{\an5\pos(540,1050)" +
            r"\fscx86\fscy86\t(0,90,\fscx100\fscy100)" +
            r"\bord5\shad1\fs72}" + phrase
        )
        events.append(f"Dialogue: 0,{fmt_ts(start)},{fmt_ts(end)},PopCap,,0,0,0,,{caption}")

    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return out_ass


def _score_motion_windows(src_video, source_dur, segment_dur, step=1.0):
    """Rank candidate source windows by decoded frame-to-frame luminance change."""
    width, height = 160, 90
    frame_size = width * height
    decoded = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src_video,
         "-vf", f"fps=2,scale={width}:{height}:flags=area,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180
    ).stdout
    frame_count = len(decoded) // frame_size
    if frame_count < 4:
        raise RuntimeError("Not enough decoded frames to score motion.")
    frames = [decoded[i * frame_size:(i + 1) * frame_size] for i in range(frame_count)]
    diffs = [0.0]
    for i in range(1, frame_count):
        diffs.append(sum(abs(a - b) for a, b in zip(frames[i - 1], frames[i])) / frame_size)
    candidates, start = [], 0.0
    latest = max(0.0, source_dur - segment_dur)
    while start <= latest + 0.001:
        lo, hi = max(1, int(start * 2)), min(frame_count, max(2, int((start + segment_dur) * 2)))
        score = sum(diffs[lo:hi]) / max(1, hi - lo)
        candidates.append((score, start))
        start += step
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = [candidates[0][1]] if candidates else [0.0]
    for _, candidate in candidates[1:]:
        if all(abs(candidate - chosen) >= segment_dur * 0.85 for chosen in selected):
            selected.append(candidate)
        if len(selected) >= 12:
            break
    return selected


def render_full_bleed_short(src_video, script_text, out_video="/tmp/final_short.mp4", top_hook="", creative_angle="clip_focused"):
    """Render a 22–28 second vertical Short with motion-ranked action-first cuts."""
    if not os.path.isfile(src_video) or os.path.getsize(src_video) < 100_000:
        raise RuntimeError(f"Source video is missing or too small: {src_video}")
    tts_result = synthesize_human_voice(script_text)
    mp3_path, audio_dur, voice_used = tts_result[:3]
    word_boundaries = tts_result[3] if len(tts_result) > 3 else None
    if not (22.0 <= audio_dur <= 28.0):
        raise RuntimeError(f"Narration must be 22–28 seconds at natural pacing; got {audio_dur:.2f}s.")

    target_dur = audio_dur
    cut_count = max(1, int((target_dur + 3.49) // 3.5))
    segment_dur = target_dur / cut_count
    if not (3.0 <= segment_dur <= 4.0):
        raise RuntimeError(f"Invalid fast-cut length: {segment_dur:.2f}s.")

    fitted_voice = "/tmp/voice_fitted.mp3"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", mp3_path,
        "-t", str(target_dur), "-filter:a", "atempo=1.0",
        "-c:a", "libmp3lame", "-q:a", "3", fitted_voice
    ], check=True, timeout=120)
    fitted_boundaries = [
        {"text": item.get("text", ""), "start": float(item.get("start", 0)),
         "duration": float(item.get("duration", 0))}
        for item in word_boundaries
    ] if word_boundaries else None
    ass_path = build_clean_ass_captions(
        script_text, target_dur, word_boundaries=fitted_boundaries
    )

    source_dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", src_video
    ], text=True, timeout=60).strip())
    if source_dur < segment_dur:
        raise RuntimeError("Gameplay source is shorter than one required cut.")
    cut_starts = _score_motion_windows(src_video, source_dur, segment_dur)
    if len(cut_starts) < cut_count:
        for candidate in [i * segment_dur for i in range(int(source_dur // segment_dur) + 1)]:
            if candidate + segment_dur <= source_dur and all(
                abs(candidate - chosen) >= segment_dur * 0.85 for chosen in cut_starts
            ):
                cut_starts.append(candidate)
            if len(cut_starts) >= cut_count:
                break
    if len(cut_starts) < cut_count:
        raise RuntimeError("Could not find enough distinct source windows for fast cuts.")
    cut_starts = cut_starts[:cut_count]

    hook_path = "/tmp/hook_banner.txt"
    with open(hook_path, "w", encoding="utf-8") as hook_file:
        hook_file.write(re.sub(r"\s+", " ", str(top_hook or "")).strip()[:100])
    cut_filters, cut_labels = [], []
    for index, cut_start in enumerate(cut_starts):
        label = f"cut{index}"
        cut_labels.append(f"[{label}]")
        cut_filters.append(
            f"[0:v]trim=start={cut_start:.3f}:duration={segment_dur:.3f},"
            "setpts=PTS-STARTPTS,fps=30,"
            "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,"
            "zoompan=z='min(1.05,1+0.05*on/105)':d=1:s=1080x1920:fps=30,"
            f"setsar=1[{label}]"
        )
    concat_inputs = "".join(cut_labels)
    filter_graph = (
        ";".join(cut_filters) + ";" +
        f"{concat_inputs}concat=n={cut_count}:v=1:a=0[game];"
        "[game]unsharp=5:5:0.8:5:5:0.0,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"textfile={hook_path}:fontcolor=white:fontsize=46:box=1:"
        f"boxcolor=black@0.82:boxborderw=18:x=(w-text_w)/2:y=250:"
        f"enable='between(t,0,2.5)':alpha='if(lt(t,2.1),1,max(0,(2.5-t)/0.4))',"
        f"ass={ass_path}[outv]"
    )
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", src_video, "-i", fitted_voice,
        "-f", "lavfi", "-t", "0.35", "-i",
        "anoisesrc=color=pink:amplitude=0.12:sample_rate=44100",
        "-f", "lavfi", "-t", "0.35", "-i",
        "sine=frequency=85:sample_rate=44100",
        "-filter_complex",
        filter_graph + ";"
        "[2:a]highpass=f=700,lowpass=f=9000,afade=t=out:st=0.16:d=0.19,volume=-12dB[impact];"
        "[3:a]lowpass=f=140,afade=t=out:st=0.12:d=0.23,volume=-12dB[sub];"
        "[impact][sub]amix=inputs=2:duration=longest:normalize=0[hookfx];"
        "[1:a][hookfx]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "loudnorm=I=-14:TP=-1.5:LRA=11[aout]",
        "-map", "[outv]", "-map", "[aout]",
        "-t", str(target_dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", out_video
    ]
    subprocess.run(command, check=True, timeout=540)
    if not os.path.isfile(out_video) or os.path.getsize(out_video) < 100_000:
        raise RuntimeError("FFmpeg completed without producing a valid output video.")
    output_duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", out_video
    ], text=True, timeout=60).strip())
    if abs(output_duration - target_dur) > 0.25:
        raise RuntimeError(f"Rendered duration mismatch: expected {target_dur:.2f}s, got {output_duration:.2f}s")
    print(
        f"Rendered {output_duration:.2f}s Short; {cut_count} motion-ranked "
        f"{segment_dur:.2f}s cuts, highest-motion first, 1.00–1.05 zoom, "
        "full-bleed 9:16 and 72px centered captions."
    )
    return out_video
