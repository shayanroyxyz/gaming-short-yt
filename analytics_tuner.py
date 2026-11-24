"""Daily, best-effort YouTube upload analytics tuner.

Uses the repository's existing OAuth refresh-token secrets and the free YouTube
Data API. If the refresh token lacks read scope, the failure is recorded and
normal upload generation continues unchanged.
"""
import datetime
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def tune_daily_analytics(config, history):
    now = datetime.datetime.now(datetime.timezone.utc)
    last = config.get("analytics_last_attempt_at")
    if last:
        try:
            last_dt = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - last_dt).total_seconds() < 86400:
                return False
        except (TypeError, ValueError):
            pass

    config["analytics_last_attempt_at"] = now.isoformat()
    api_key = (os.environ.get("YOUTUBE_API_KEY", "").strip()
               or os.environ.get("GEMINI_API_KEY", "").strip())
    if not api_key:
        config["analytics_last_error"] = "Missing YOUTUBE_API_KEY (or fallback GEMINI_API_KEY)."
        print("[analytics] Skipped: " + config["analytics_last_error"])
        return False

    try:
        youtube = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        video_ids = []
        for bucket in ("uploaded_source_windows", "used_source_windows"):
            for entry in history.get(bucket, []):
                if isinstance(entry, dict) and entry.get("video_id"):
                    video_ids.append(str(entry["video_id"]))
        for entry in history.get("recent_creative_entries", []):
            if isinstance(entry, dict) and entry.get("video_id"):
                video_ids.append(str(entry["video_id"]))
        video_ids = list(dict.fromkeys(video_ids))[-50:]
        if not video_ids:
            raise RuntimeError("No previously uploaded video IDs are stored in history.json.")

        videos_response = youtube.videos().list(
            part="snippet,statistics", id=",".join(video_ids), maxResults=50
        ).execute()
        creative_by_video = {
            str(entry.get("video_id")): entry
            for entry in history.get("recent_creative_entries", [])
            if isinstance(entry, dict) and entry.get("video_id")
        }

        ranked = []
        for item in videos_response.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            views = int(stats.get("viewCount", 0) or 0)
            likes = int(stats.get("likeCount", 0) or 0)
            comments = int(stats.get("commentCount", 0) or 0)
            like_ratio = likes / max(views, 1)
            score = views * (1.0 + min(like_ratio, 0.25) * 4.0) + likes * 2 + comments * 20
            video_id = item.get("id", "")
            creative = creative_by_video.get(video_id, {})
            ranked.append({
                "video_id": video_id, "title": snippet.get("title", ""),
                "hook": creative.get("hook", ""), "angle": creative.get("angle", ""),
                "views": views, "likes": likes, "comments": comments,
                "like_ratio": round(like_ratio, 5), "score": round(score, 2),
            })

        if not ranked:
            raise RuntimeError("YouTube Data API returned no accessible public videos for saved IDs.")
        ranked.sort(key=lambda row: row["score"], reverse=True)
        config["winning_examples"] = ranked[:3]
        config["analytics_last_success_at"] = now.isoformat()
        config.pop("analytics_last_error", None)
        print(f"[analytics] Refreshed {len(ranked)} saved public video IDs; saved top {len(config['winning_examples'])}.")
        return True
    except Exception as exc:
        config["analytics_last_error"] = f"{type(exc).__name__}: {exc}"
        print(
            "[analytics] Read failed; preserving previous winning_examples. "
            f"Check whether the existing refresh token includes youtube.readonly: "
            f"{config['analytics_last_error']}"
        )
        return False
