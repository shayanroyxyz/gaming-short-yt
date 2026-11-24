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
    required = ("YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        config["analytics_last_error"] = "Missing OAuth environment variables: " + ", ".join(missing)
        print("[analytics] Skipped: " + config["analytics_last_error"])
        return False

    try:
        credentials = Credentials(
            token=None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token"
        )
        credentials.refresh(Request())
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

        channel_response = youtube.channels().list(
            part="contentDetails", mine=True, maxResults=1
        ).execute()
        channels = channel_response.get("items", [])
        if not channels:
            raise RuntimeError("YouTube API returned no channel for the current OAuth identity.")
        uploads_playlist = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        playlist_response = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_playlist, maxResults=20
        ).execute()
        video_ids = [
            item.get("contentDetails", {}).get("videoId")
            for item in playlist_response.get("items", [])
        ]
        video_ids = [video_id for video_id in video_ids if video_id]
        if not video_ids:
            raise RuntimeError("No recent uploads were returned by the uploads playlist.")

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
            # Engagement-weighted ranking, not a claim of algorithmic virality.
            score = views * (1.0 + min(like_ratio, 0.25) * 4.0) + likes * 2 + comments * 20
            video_id = item.get("id", "")
            creative = creative_by_video.get(video_id, {})
            ranked.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "hook": creative.get("hook", ""),
                "angle": creative.get("angle", ""),
                "views": views,
                "likes": likes,
                "comments": comments,
                "like_ratio": round(like_ratio, 5),
                "score": round(score, 2),
            })

        ranked.sort(key=lambda row: row["score"], reverse=True)
        config["winning_examples"] = ranked[:3]
        config["analytics_last_success_at"] = now.isoformat()
        config.pop("analytics_last_error", None)
        print(
            f"[analytics] Refreshed {len(ranked)} recent uploads; "
            f"saved {len(config['winning_examples'])} measured winning examples."
        )
        return True
    except Exception as exc:
        config["analytics_last_error"] = f"{type(exc).__name__}: {exc}"
        print(
            "[analytics] Read failed; preserving previous winning_examples. "
            f"Check whether the existing refresh token includes youtube.readonly: "
            f"{config['analytics_last_error']}"
        )
        return False
